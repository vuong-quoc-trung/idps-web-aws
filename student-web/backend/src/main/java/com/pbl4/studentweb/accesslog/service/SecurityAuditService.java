package com.pbl4.studentweb.accesslog.service;

import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class SecurityAuditService {
    private final AuditDatabaseWriter database;
    private final AuditJsonlExporter exporter;
    private static final org.slf4j.Logger LOG = org.slf4j.LoggerFactory.getLogger(SecurityAuditService.class);

    public void record(AuditEvent event) {
        try { database.record(event); }
        catch (RuntimeException e) {
            String state = "unknown";
            Throwable cause = e;
            for (int depth = 0; cause != null && depth < 16; depth++, cause = cause.getCause()) {
                if (cause instanceof java.sql.SQLException sql) { state = sql.getSQLState(); break; }
            }
            // Never include exception text, request fields, paths or secrets in this warning.
            LOG.warn("Security audit database write failed: type={}, SQLSTATE={}", e.getClass().getSimpleName(), state);
        }
        try { exporter.append(event); }
        catch (java.io.IOException | RuntimeException e) {
            LOG.warn("Security audit JSONL write failed: type={}; inspect exporter permissions/capacity", e.getClass().getSimpleName());
        }
    }
}
