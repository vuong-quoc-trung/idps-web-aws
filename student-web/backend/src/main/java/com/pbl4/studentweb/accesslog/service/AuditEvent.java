package com.pbl4.studentweb.accesslog.service;

import com.pbl4.studentweb.configuration.RequestAttribution;
import java.time.Instant;
import java.util.UUID;

/** Request metadata only. Identity values stay in memory until pseudonymized by the exporter. */
public record AuditEvent(String eventId, Instant timestamp, String requestId, String clientIp, String peerIp,
        Long userId, String username, String role, String sessionId, String httpMethod, String uriPath,
        String queryString, int statusCode, long latencyMs, String userAgent, boolean truncated) {
    private static final java.util.List<String> USER_AGENT_PRODUCTS = java.util.List.of(
        "sqlmap", "nikto", "dirbuster", "gobuster", "masscan", "acunetix", "nmap", "zgrab", "nuclei", "ffuf",
        "Mozilla", "Chromium", "Chrome", "Firefox", "Safari", "Edge", "curl", "wget", "python-requests",
        "PostmanRuntime", "Go-http-client");

    public AuditEvent {
        if (eventId == null) eventId = UUID.randomUUID().toString();
        if (timestamp == null) timestamp = Instant.now();
        truncated = truncated || tooLong(httpMethod, 10) || tooLong(uriPath, 500)
                || tooLong(queryString, 1024) || tooLong(userAgent, 512) || parameterCount(queryString) > 32;
        requestId = RequestAttribution.validRequestId(requestId) ? requestId : null;
        clientIp = clean(clientIp, 45);
        peerIp = clean(peerIp, 45);
        httpMethod = httpMethod != null && java.util.Set.of("GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH",
            "DELETE", "CONNECT", "TRACE", "OTHER").contains(httpMethod) ? httpMethod : "OTHER";
        uriPath = path(uriPath);
        queryString = query(queryString);
        userAgent = safeUserAgent(userAgent);
        if (role != null && !java.util.Set.of("ADMIN", "STAFF", "STUDENT").contains(role)) role = null;
        latencyMs = Math.max(0, latencyMs);
    }

    private static String safeUserAgent(String raw) {
        if (raw == null) return null;
        String lower = clean(raw, 512).toLowerCase(java.util.Locale.ROOT);
        if (lower.isBlank()) return "";
        // Never retain arbitrary header prose, even when it resembles a valid UA.
        var products = USER_AGENT_PRODUCTS.stream().filter(product -> lower.contains(
            product.equals("Edge") ? "edg/" : product.toLowerCase(java.util.Locale.ROOT))).toList();
        return products.isEmpty() ? "[REDACTED]" : String.join(" ", products);
    }

    private static boolean tooLong(String value, int limit) { return value != null && value.length() > limit; }
    private static int parameterCount(String query) {
        if (query == null || query.isEmpty()) return 0;
        int result = 1;
        for (int i = 0; i < Math.min(query.length(), 1024); i++) if (query.charAt(i) == '&') result++;
        return result;
    }
    private static String clean(String value, int limit) {
        if (value == null) return null;
        var result = new StringBuilder();
        value.codePoints().limit(limit).filter(c -> !Character.isISOControl(c) && c != 0x2028 && c != 0x2029
                && !(c >= 0xD800 && c <= 0xDFFF)).forEach(result::appendCodePoint);
        return result.toString();
    }
    private static String path(String raw) {
        if (raw == null) return "/";
        String value = clean(raw, 500);
        // Neither query/fragment text nor matrix/session parameters belong in the path view.
        String lower = value.toLowerCase(java.util.Locale.ROOT);
        int end = value.length();
        for (String delimiter : new String[]{"?", "#", "%3f", "%23"}) {
            int index = lower.indexOf(delimiter);
            if (index >= 0) end = Math.min(end, index);
        }
        value = value.substring(0, end).replaceAll("(?i)(?:;|%3b)[^/]*", "");
        var result = new StringBuilder();
        var allowed = java.util.Set.of("api", "auth", "login", "logout", "csrf", "me", "profile", "completion", "academic", "classmates", "students", "users", "faculties", "majors", "classes", "training-programs", "addresses", "family-members", "emergency-contacts", "post-graduation-contacts", "profile-options", "access-logs", "activate", "activation", "verify", "send", "forgot-password", "reset-password", "change-password");
        for (String segment : value.split("/")) {
            if (segment.isEmpty()) continue;
            result.append('/').append(allowed.contains(segment) ? segment : segment.matches("[0-9]+") ? "[id]" : "[redacted]");
        }
        return result.isEmpty() ? "/" : result.toString();
    }
    private static String query(String raw) {
        if (raw == null) return null;
        if (raw.isEmpty()) return "";
        String bounded = raw.substring(0, Math.min(1024, raw.length()));
        String[] parameters = bounded.split("&", -1);
        var result = new StringBuilder();
        for (int i = 0; i < Math.min(parameters.length, 32); i++) {
            String parameter = parameters[i];
            int equals = parameter.indexOf('=');
            String key = equals < 0 ? parameter : parameter.substring(0, equals);
            if (!java.util.Set.of("q", "search", "page", "size", "sort", "direction", "id", "classId", "facultyId", "majorId", "token", "password", "secret", "code").contains(key)) key = "[REDACTED_KEY]";
            if (i > 0) result.append('&');
            result.append(key).append("=[REDACTED]");
        }
        return result.toString();
    }

    @Override public String toString() { return "AuditEvent[redacted]"; }
}
