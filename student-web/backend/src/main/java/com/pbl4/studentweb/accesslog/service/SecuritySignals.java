package com.pbl4.studentweb.accesslog.service;

import jakarta.servlet.http.HttpServletRequest;
import java.util.LinkedHashSet;
import java.util.Set;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

/** Server decisions only. Values remain request-local until HMAC export. Never log this object. */
public final class SecuritySignals {
    private static final String ATTRIBUTE = SecuritySignals.class.getName();
    public enum Reason { LOGIN_FAILED, OBJECT_ACCESS_DENIED, MASS_ASSIGNMENT, PRIVILEGE_DENIED, INVALID_SESSION, SESSION_REVOKED, WORKFLOW_DENIED, RATE_LIMITED, CSRF_INVALID, RECOVERY_TOKEN_INVALID }
    private final Set<Reason> reasons = new LinkedHashSet<>();
    private String account, object;
    private final Set<String> fields = new LinkedHashSet<>();
    public static SecuritySignals get(HttpServletRequest request) {
        var existing = (SecuritySignals) request.getAttribute(ATTRIBUTE);
        if (existing == null) { existing = new SecuritySignals(); request.setAttribute(ATTRIBUTE, existing); }
        return existing;
    }
    public static void objectDenied(String type, Long id) {
        if (RequestContextHolder.getRequestAttributes() instanceof ServletRequestAttributes attrs) {
            var signal = get(attrs.getRequest());
            signal.reasons.add(Reason.OBJECT_ACCESS_DENIED);
            signal.object = type + ":" + id;
        }
    }
    public static void markCurrent(Reason reason) {
        if (RequestContextHolder.getRequestAttributes() instanceof ServletRequestAttributes attrs)
            get(attrs.getRequest()).mark(reason);
    }
    public void mark(Reason reason) { reasons.add(reason); }
    public void loginFailed(String attempted) {
        mark(Reason.LOGIN_FAILED);
        // Match authentication's exact username semantics. Oversized identities aren't aggregated.
        if (attempted != null && !attempted.isBlank() && attempted.length() <= 50) account = attempted;
    }
    public void forbiddenField(String field) {
        if (Set.of("role", "isAdmin", "ownerId", "userId", "studentId", "authorities", "permissions").contains(field)) {
            mark(Reason.MASS_ASSIGNMENT); fields.add(field);
        }
    }
    public Set<Reason> reasons() { return Set.copyOf(reasons); }
    public Set<String> fields() { return Set.copyOf(fields); }
    public String account() { return account; }
    public String object() { return object; }
    @Override public String toString() { return "SecuritySignals[redacted]"; }
}
