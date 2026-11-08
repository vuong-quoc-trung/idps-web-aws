package com.pbl4.studentweb.configuration;

import com.pbl4.studentweb.accesslog.service.SecurityAuditService;
import com.pbl4.studentweb.accesslog.service.AuditEvent;
import java.time.Instant;
import java.util.UUID;
import jakarta.servlet.*;
import jakarta.servlet.http.*;
import java.io.IOException;
import java.util.Set;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

final class SecurityRequestFilter extends OncePerRequestFilter {
    private static final org.slf4j.Logger LOG = org.slf4j.LoggerFactory.getLogger(SecurityRequestFilter.class);

    private static void failureMetadata(Exception error, HttpServletRequest request, String requestId, boolean authenticated, int status) {
        if (!LOG.isDebugEnabled()) return;
        String origin = "unclassified";
        String stage = "unclassified";
        for (var frame : error.getStackTrace()) {
            if (origin.equals("unclassified") && frame.getClassName().startsWith("org.springframework.security.")) {
                origin = frame.getClassName() + "." + frame.getMethodName();
            }
            if (frame.getClassName().startsWith("org.springframework.security.web.authentication.")
                    || frame.getClassName().startsWith("org.springframework.security.web.csrf.")) {
                stage = frame.getClassName() + "." + frame.getMethodName();
                break;
            }
        }
        // Class/stage metadata only: never exception messages, values or stack dumps.
        int declaredStatus = error instanceof org.apache.tomcat.util.http.InvalidParameterException invalid ? invalid.getErrorCode() : 0;
        LOG.debug("Request chain failed: type={}, dispatch={}, request_id={}, entry_authenticated={}, observed_status={}, origin={}, declared_parameter_status={}, stage={}",
                error.getClass().getName(), request.getDispatcherType(), requestId, authenticated, status, origin, declaredStatus, stage);
    }
    private static final Set<String> LIMITED = Set.of("/api/auth/login", "/api/auth/activate", "/api/auth/activation/verify", "/api/auth/activation/send",
        "/api/auth/forgot-password", "/api/auth/reset-password", "/api/auth/change-password");
    private final SensitiveRequestLimiter limiter;
    private final SecurityAuditService audit;
    private final RequestAttribution attribution;
    private final boolean includeReads;
    SecurityRequestFilter(SensitiveRequestLimiter limiter, SecurityAuditService audit, RequestAttribution attribution, boolean includeReads) {
        this.limiter = limiter; this.audit = audit; this.attribution = attribution; this.includeReads = includeReads;
    }
    private org.springframework.security.core.Authentication identity() {
        var auth = SecurityContextHolder.getContext().getAuthentication();
        return auth == null || !auth.isAuthenticated() || auth instanceof AnonymousAuthenticationToken ? null : auth;
    }
    private String actor() {
        var auth = SecurityContextHolder.getContext().getAuthentication();
        return auth == null || !auth.isAuthenticated() || auth instanceof AnonymousAuthenticationToken ? null : auth.getName();
    }
    @Override protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String path = request.getRequestURI().substring(request.getContextPath().length());
        String method = request.getMethod();
        boolean mutation = !Set.of("GET", "HEAD", "OPTIONS").contains(method);
        var before = identity();
        var client = attribution.resolve(request);
        response.setHeader("X-Request-Id", client.requestId());
        long start = System.nanoTime();
        boolean failed = false;
        try {
            if ("POST".equals(method) && LIMITED.contains(path)
                    && !limiter.allow(client.clientIp() + "|" + path, path.endsWith("forgot-password") ? 5 : 20)) {
                com.pbl4.studentweb.accesslog.service.SecuritySignals.get(request).mark(
                    com.pbl4.studentweb.accesslog.service.SecuritySignals.Reason.RATE_LIMITED);
                response.setHeader("Retry-After", "60");
                SecurityConfiguration.error(response, 429, "Too many requests; try again later");
                return;
            }
            chain.doFilter(request, response);
        } catch (ServletException | RuntimeException e) {
            failed = true;
            failureMetadata(e, request, client.requestId(), before != null, response.getStatus());
            if (response.isCommitted()) throw e;
            // Parameter parsing can fail in security filters, before MVC advice.
            // Trust only the container's explicit parser status; other exceptions
            // remain genuine server errors, never inferred from exception messages.
            int status = 500;
            if (e instanceof org.apache.tomcat.util.http.InvalidParameterException invalid
                    && (invalid.getErrorCode() == 400 || invalid.getErrorCode() == 413)) {
                status = invalid.getErrorCode();
            }
            // resetBuffer alone retains stale framing (e.g. an old Content-Length).
            // Preserve security/session/identity headers, then start a clean body.
            var headers = new java.util.LinkedHashMap<String, java.util.List<String>>();
            var entity = Set.of("content-length", "transfer-encoding", "content-encoding", "content-type");
            for (String name : response.getHeaderNames()) {
                if (!entity.contains(name.toLowerCase(java.util.Locale.ROOT)))
                    headers.put(name, java.util.List.copyOf(response.getHeaders(name)));
            }
            response.reset();
            headers.forEach((name, values) -> values.forEach(value -> response.addHeader(name, value)));
            SecurityConfiguration.error(response, status, status == 500 ? "Internal server error" : "Invalid request data");
            failed = false; // Completed response: audit its observed status, not synthetic500.
        } catch (IOException e) {
            failed = true;
            failureMetadata(e, request, client.requestId(), before != null, response.getStatus());
            throw e;
        }
        finally {
            if (path.startsWith("/api/") && (includeReads || mutation || response.getStatus() >= 400 || failed)) {
                var auth = identity();
                if (auth == null) auth = before;
                String username = auth == null ? null : auth.getName();
                Long userId = auth != null && auth.getPrincipal() instanceof AccountPrincipal principal ? principal.userId() : null;
                String role = auth == null ? null : auth.getAuthorities().stream().map(a -> a.getAuthority())
                        .filter(a -> a.startsWith("ROLE_")).map(a -> a.substring(5)).findFirst().orElse(null);
                var session = request.getSession(false);
                audit.record(new AuditEvent(UUID.randomUUID().toString(), Instant.now(), client.requestId(), client.clientIp(), client.peerIp(),
                    userId, username, role, session == null ? null : session.getId(), method, path, request.getQueryString(),
                    failed ? 500 : response.getStatus(), (System.nanoTime() - start) / 1000000, request.getHeader("User-Agent"), false), com.pbl4.studentweb.accesslog.service.SecuritySignals.get(request));
            }
        }
    }
}
