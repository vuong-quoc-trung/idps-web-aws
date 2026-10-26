package com.pbl4.studentweb.accesslog.service;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.*;
import java.util.*;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import tools.jackson.databind.json.JsonMapper;

/** Bounded synchronous JSONL writer. Reopening each append follows rename/create rotation. */
@Component
public class AuditJsonlExporter {
    public static final int MAX_LINE_BYTES = 16 * 1024;
    private static final Set<PosixFilePermission> FILE_MODE = PosixFilePermissions.fromString("rw-------");
    private static final Set<PosixFilePermission> DIR_MODE = PosixFilePermissions.fromString("rwx------");
    private final boolean enabled;
    private final Path path;
    private final String sourceInstance;
    private final byte[] key;
    private final long maxFileBytes;
    private final JsonMapper mapper;

    public AuditJsonlExporter(JsonMapper mapper, @Value("${app.audit.file.enabled:false}") boolean enabled,
            @Value("${app.audit.file.path:./logs/audit.log}") String path,
            @Value("${app.audit.source-instance:student-web}") String sourceInstance,
            @Value("${app.audit.file.hmac-key:}") String hmacKey,
            @Value("${app.audit.file.max-bytes:67108864}") long maxFileBytes) {
        this.mapper = mapper;
        this.enabled = enabled;
        this.path = Path.of(path).toAbsolutePath().normalize();
        this.sourceInstance = sourceInstance;
        this.key = hmacKey.getBytes(StandardCharsets.UTF_8);
        this.maxFileBytes = maxFileBytes;
        if (enabled && (key.length < 32 || maxFileBytes < MAX_LINE_BYTES
                || !sourceInstance.matches("[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")))
            throw new IllegalArgumentException("Audit JSONL requires a >=32-byte HMAC key, valid source instance and file limit >=16384");
    }

    public synchronized void append(AuditEvent event) throws IOException {
        if (!enabled) return;
        byte[] json = mapper.writeValueAsBytes(envelope(event));
        if (json.length + 1 > MAX_LINE_BYTES) throw new IOException("Audit JSONL line exceeds configured safety limit");
        Path parent = path.getParent();
        Files.createDirectories(parent, PosixFilePermissions.asFileAttribute(DIR_MODE));
        // Private directory prevents replacement of the target while applying permissions/opening.
        var directory = Files.readAttributes(parent, PosixFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
        var owner = parent.getFileSystem().getUserPrincipalLookupService()
                .lookupPrincipalByName(System.getProperty("user.name"));
        if (!directory.isDirectory() || !directory.owner().equals(owner)
                || directory.permissions().contains(PosixFilePermission.GROUP_WRITE)
                || directory.permissions().contains(PosixFilePermission.OTHERS_WRITE))
            throw new IOException("Audit JSONL parent directory must be owned by the application and not shared-writable");
        boolean existed = Files.exists(path, LinkOption.NOFOLLOW_LINKS);
        if (existed) {
            var attributes = Files.readAttributes(path, PosixFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
            if (!attributes.isRegularFile() || !attributes.owner().equals(owner))
                throw new IOException("Audit JSONL target must be an application-owned regular file");
            Files.setPosixFilePermissions(path, FILE_MODE);
        }
        try (var channel = FileChannel.open(path,
                Set.of(StandardOpenOption.CREATE, StandardOpenOption.WRITE, StandardOpenOption.APPEND, LinkOption.NOFOLLOW_LINKS),
                PosixFilePermissions.asFileAttribute(FILE_MODE)); var lock = channel.lock()) {
            long originalSize = channel.size();
            if (originalSize + json.length + 1 > maxFileBytes)
                throw new IOException("Audit JSONL file limit reached; rotation is required");
            byte[] line = Arrays.copyOf(json, json.length + 1);
            line[line.length - 1] = '\n';
            try {
                var bytes = ByteBuffer.wrap(line);
                while (bytes.hasRemaining()) channel.write(bytes);
                channel.force(true);
            } catch (IOException failure) {
                try { channel.truncate(originalSize); channel.force(true); }
                catch (IOException rollbackFailure) { failure.addSuppressed(rollbackFailure); }
                throw failure;
            }
        }
        if (!existed) {
            try (var directoryChannel = FileChannel.open(parent, StandardOpenOption.READ)) { directoryChannel.force(true); }
        }
    }

    private Map<String, Object> envelope(AuditEvent event) {
        var result = new LinkedHashMap<String, Object>();
        result.put("schema_version", "1.0");
        result.put("event_id", event.eventId());
        result.put("source", "STUDENT_AUDIT");
        result.put("source_instance", sourceInstance);
        result.put("timestamp", event.timestamp().toString());
        result.put("request_id", event.requestId());
        result.put("client_ip", event.clientIp());
        result.put("peer_ip", event.peerIp());
        result.put("user_id", pseudonym("user_id", event.userId() == null ? null : event.userId().toString()));
        result.put("username", pseudonym("username", event.username()));
        result.put("role", event.role());
        result.put("session_hmac", pseudonym("session", event.sessionId()));
        result.put("http_method", event.httpMethod());
        result.put("uri_path", event.uriPath());
        result.put("query_string", event.queryString());
        result.put("status_code", event.statusCode());
        result.put("latency_ms", event.latencyMs());
        result.put("user_agent", event.userAgent());
        result.put("event_type", "http_request");
        result.put("outcome", event.statusCode() >= 400 ? "failure" : "success");
        result.put("dest_ip", null);
        result.put("src_port", null);
        result.put("dest_port", null);
        result.put("transport", "HTTP");
        result.put("flow_id", null);
        result.put("request_bytes", null);
        result.put("response_bytes", null);
        result.put("flow", null);
        result.put("redacted", true);
        result.put("truncated", event.truncated());
        return result;
    }

    private String pseudonym(String purpose, String value) {
        if (value == null) return null;
        try {
            var mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(key, "HmacSHA256"));
            return "hmac-sha256:" + HexFormat.of().formatHex(mac.doFinal((purpose + ":" + value).getBytes(StandardCharsets.UTF_8)));
        } catch (java.security.GeneralSecurityException e) {
            throw new IllegalStateException("Audit pseudonymization is unavailable");
        }
    }
}
