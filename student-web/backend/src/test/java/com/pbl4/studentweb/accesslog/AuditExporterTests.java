package com.pbl4.studentweb.accesslog;

import com.pbl4.studentweb.accesslog.service.*;
import java.nio.file.*;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import tools.jackson.databind.json.JsonMapper;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

class AuditExporterTests {
    @TempDir Path directory;
    private final JsonMapper json = JsonMapper.builder().build();
    private AuditEvent event() {
        return new AuditEvent("event-123", Instant.parse("2026-10-26T00:00:00Z"), "edge-123", "192.0.2.1", "127.0.0.1", 42L,
            "CANARY_USERNAME", "STUDENT", "CANARY_SESSION", "GET", "/api/students;jsessionid=CANARY_SESSION", "token=CANARY_TOKEN&password=CANARY_PASSWORD&q=CANARY_SEARCH&CANARY_KEY=1", 200, 15,
            "Bearer CANARY_HEADER", false);
    }
    private AuditJsonlExporter exporter(Path path, long max) {
        return new AuditJsonlExporter(json,true,path.toString(),"student-web","test-only-hmac-key-at-least-32-bytes",max);
    }
    @Test void writesCanonicalUtcJsonlWithoutSecretsAndWithPseudonyms() throws Exception {
        Path path=directory.resolve("student-audit.log"); exporter(path,65536).append(event());
        String line=Files.readString(path); assertThat(line.lines().count()).isEqualTo(1);
        assertThat(line).doesNotContain("CANARY"); var node=json.readTree(line);
        assertThat(node.path("schema_version").asText()).isEqualTo("1.0");
        assertThat(node.path("timestamp").asText()).isEqualTo("2026-10-26T00:00:00Z");
        assertThat(node.path("request_id").asText()).isEqualTo("edge-123");
        assertThat(node.path("user_id").asText()).matches("hmac-sha256:[a-f0-9]{64}");
        assertThat(node.path("username").asText()).matches("hmac-sha256:[a-f0-9]{64}");
        assertThat(node.path("session_hmac").asText()).matches("hmac-sha256:[a-f0-9]{64}");
        assertThat(node.path("user_id").asText()).isNotEqualTo(node.path("username").asText());
        assertThat(Files.getPosixFilePermissions(path)).doesNotContain(java.nio.file.attribute.PosixFilePermission.OTHERS_READ);
    }
    @Test void followsRenameCreateRotationAndDoesNotOverwriteWhenFull() throws Exception {
        Path path=directory.resolve("audit.log"); var writer=exporter(path,16384);
        writer.append(event()); var rotated=directory.resolve("audit.log.1");Files.move(path,rotated);writer.append(event());
        assertThat(Files.readString(rotated).lines().count()).isEqualTo(1);assertThat(Files.readString(path).lines().count()).isEqualTo(1);
        Files.writeString(path,"X".repeat(16384));assertThatThrownBy(()->writer.append(event())).isInstanceOf(java.io.IOException.class);
        assertThat(Files.size(path)).isEqualTo(16384);
    }
    @Test void rejectsSymlinkAndWeakKeyAndStillExportsWhenDatabaseFails() throws Exception {
        Path target=directory.resolve("target");Files.writeString(target,"unchanged");Path link=directory.resolve("audit.log");Files.createSymbolicLink(link,target);
        assertThatThrownBy(()->exporter(link,65536).append(event())).isInstanceOf(java.io.IOException.class);assertThat(Files.readString(target)).isEqualTo("unchanged");
        assertThatThrownBy(()->new AuditJsonlExporter(json,true,target.toString(),"student-web","short",65536)).isInstanceOf(IllegalArgumentException.class);
        var db=mock(AuditDatabaseWriter.class);var file=mock(AuditJsonlExporter.class);doThrow(new IllegalStateException("CANARY_DB_SECRET")).when(db).record(any());
        var e=event();new SecurityAuditService(db,file).record(e);verify(file).append(e);
    }
    @Test void suppressesBareSecretsInUnknownAndRecognizedUserAgentsAndCustomMethods() throws Exception {
        Path path = directory.resolve("privacy.log"); var writer = exporter(path, 65536);
        for (String ua : new String[]{"BARE_CANARY_SECRET@example.invalid", "Mozilla/5.0 Chrome/123 BARE_CANARY_SECRET", "nuclei/3 BARE_CANARY_SECRET"}) {
            var e = new AuditEvent(null, null, "edge-privacy", "192.0.2.1", "127.0.0.1", null, null, null, null,
                "CANARY", "/api/faculties", null, 405, 1, ua, false);
            assertThat(e.userAgent()).isIn("[REDACTED]", "Mozilla Chrome", "nuclei");
            assertThat(e.httpMethod()).isEqualTo("OTHER");
            writer.append(e);
        }
        assertThat(Files.readString(path)).doesNotContain("CANARY");
        assertThat(Files.readString(path).lines().count()).isEqualTo(3);
    }
    @Test void preservesMissingEmptyAndTruncatedUserAgentSemantics() {
        for (String ua : new String[]{null, "", " ", "Mozilla/5.0 " + "X".repeat(1024)}) {
            var e = new AuditEvent(null, null, "edge-privacy", "192.0.2.1", "127.0.0.1", null, null, null, null,
                "HEAD", "/api/faculties", null, 200, 1, ua, false);
            assertThat(e.userAgent()).isEqualTo(ua == null ? null : ua.isBlank() ? "" : "Mozilla");
            assertThat(e.truncated()).isEqualTo(ua != null && ua.length() > 512);
            assertThat(e.httpMethod()).isEqualTo("HEAD");
        }
    }
}
