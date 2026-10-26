package com.pbl4.studentweb.accesslog.service;

import com.pbl4.studentweb.accesslog.entity.AccessLog;
import com.pbl4.studentweb.accesslog.repository.AccessLogRepository;
import com.pbl4.studentweb.user.repository.UserRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Separate proxy boundary: a failed DB transaction must not suppress the JSONL write. */
@Service
@RequiredArgsConstructor
public class AuditDatabaseWriter {
    private final AccessLogRepository logs;
    private final UserRepository users;

    @Transactional
    public void record(AuditEvent event) {
        var entry = new AccessLog();
        if (event.username() != null) users.findByUsername(event.username()).ifPresent(entry::setUser);
        entry.setClientIp(event.clientIp());
        entry.setHttpMethod(event.httpMethod());
        entry.setRequestPath(event.uriPath());
        entry.setRequestId(event.requestId());
        entry.setUserAgent(event.userAgent());
        entry.setStatusCode(event.statusCode());
        entry.setAction(event.statusCode() >= 400 ? "REQUEST_REJECTED" : "REQUEST_SUCCEEDED");
        entry.setRequestTimeMs(event.latencyMs());
        logs.saveAndFlush(entry);
    }
}
