package com.pbl4.studentweb.configuration;

import com.pbl4.studentweb.accesslog.service.AuditJsonlExporter;
import jakarta.servlet.http.HttpSession;
import java.io.IOException;
import java.nio.file.*;
import java.time.Instant;
import java.util.Optional;

/** A short, operator-issued session revocation lease in a trusted local directory. */
final class DevSessionLease {
    private final Path directory;
    private final boolean accountLocks;
    private final AuditJsonlExporter audit;

    private final java.util.Set<Long> labUsers;

    DevSessionLease(String path, AuditJsonlExporter audit, boolean accountLocks) throws IOException {
        this(path, audit, accountLocks, null);
    }

    DevSessionLease(String path, AuditJsonlExporter audit, boolean accountLocks, java.util.Set<Long> labUsers) throws IOException {
        this.labUsers = labUsers;
        this.directory = Path.of(path);
        if (!directory.isAbsolute() || !directory.equals(directory.toRealPath()) || !Files.isDirectory(directory)
                || (mode(directory) & 0022) != 0)
            throw new IOException("Invalid development lease directory");
        this.audit = audit;
        this.accountLocks = accountLocks;
    }

    private static int mode(Path path) throws IOException {
        return (int) Files.getAttribute(path, "unix:mode", LinkOption.NOFOLLOW_LINKS);
    }

    boolean temporary() { return labUsers != null; }

    boolean eligible(AccountPrincipal principal) {
        return labUsers == null || (labUsers.contains(principal.userId()) && principal.getAuthorities().stream()
                .anyMatch(a -> java.util.Set.of("ROLE_STUDENT","ROLE_STAFF").contains(a.getAuthority())));
    }

    Optional<String> decision(AccountPrincipal principal, HttpSession session) throws IOException {
        if (session == null || !eligible(principal)) return Optional.empty();
        return read(directory.resolve(audit.sessionLeaseSelector(principal.userId(), session.getId())));
    }

    Optional<String> accountDecision(AccountPrincipal principal) throws IOException {
        if (principal.getAuthorities().stream().anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()))) return Optional.empty();
        return accountLocks && eligible(principal) ? read(directory.resolve(audit.accountLeaseSelector(principal.userId()))) : Optional.empty();
    }

    private Optional<String> read(Path file) throws IOException {
        if (!Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS)) return Optional.empty();
        if (!Files.getOwner(file, LinkOption.NOFOLLOW_LINKS).equals(Files.getOwner(directory))
                || (mode(file) & 0022) != 0 || Files.size(file) > 128)
            throw new IOException("Invalid development session lease");
        var fields = Files.readString(file).strip().split(" ");
        if (fields.length != 3 || !fields[0].matches("[0-9a-f]{32}")
                || !fields[1].matches("[0-9]{10}") || !fields[2].matches("[0-9]{10}"))
            throw new IOException("Invalid development session decision");
        long start = Long.parseLong(fields[1]), end = Long.parseLong(fields[2]), now = Instant.now().getEpochSecond();
        return start <= now && now < end && end-start <= 120 ? Optional.of(fields[0]) : Optional.empty();
    }
}
