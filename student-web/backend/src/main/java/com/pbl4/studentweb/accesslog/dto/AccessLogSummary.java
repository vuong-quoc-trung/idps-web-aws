package com.pbl4.studentweb.accesslog.dto;

import java.time.LocalDateTime;

public record AccessLogSummary(Long id, Long userId, String clientIp, String method, String path,
        Integer statusCode, String action, Long requestTimeMs, LocalDateTime createdAt) {}
