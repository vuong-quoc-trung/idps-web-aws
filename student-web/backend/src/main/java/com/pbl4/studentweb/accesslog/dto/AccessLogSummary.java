package com.pbl4.studentweb.accesslog.dto;

public record AccessLogSummary(Long id, String method, String path, Integer statusCode) {}
