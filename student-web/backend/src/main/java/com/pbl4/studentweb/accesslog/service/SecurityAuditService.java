package com.pbl4.studentweb.accesslog.service;

import com.pbl4.studentweb.accesslog.entity.AccessLog;
import com.pbl4.studentweb.accesslog.repository.AccessLogRepository;
import com.pbl4.studentweb.user.repository.UserRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
public class SecurityAuditService {
    private final AccessLogRepository logs;
    private final UserRepository users;
    @Transactional
    public void record(String username, String ip, String method, String path, int status, long elapsed) {
        var entry = new AccessLog();
        if (username != null) users.findByUsername(username).ifPresent(entry::setUser);
        entry.setClientIp(ip == null ? null : ip.substring(0, Math.min(45, ip.length())));
        entry.setHttpMethod(method.substring(0, Math.min(10, method.length())));
        entry.setRequestPath(path.substring(0, Math.min(500, path.length())));
        entry.setStatusCode(status);
        entry.setAction(status >= 400 ? "REQUEST_REJECTED" : "REQUEST_SUCCEEDED");
        entry.setRequestTimeMs(elapsed);
        logs.save(entry);
    }
}
