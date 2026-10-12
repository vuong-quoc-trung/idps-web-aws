package com.pbl4.studentweb.configuration;

import com.pbl4.studentweb.accesslog.service.SecurityAuditService;
import jakarta.servlet.*;
import jakarta.servlet.http.*;
import java.io.IOException;
import java.util.Set;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

final class SecurityRequestFilter extends OncePerRequestFilter {
    private static final Set<String> LIMITED = Set.of("/api/auth/login", "/api/auth/activate",
        "/api/auth/forgot-password", "/api/auth/reset-password", "/api/auth/change-password");
    private final SensitiveRequestLimiter limiter;
    private final SecurityAuditService audit;
    SecurityRequestFilter(SensitiveRequestLimiter limiter, SecurityAuditService audit) {
        this.limiter = limiter; this.audit = audit;
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
        String before = actor();
        long start = System.nanoTime();
        boolean failed = false;
        try {
            if ("POST".equals(method) && LIMITED.contains(path)
                    && !limiter.allow(request.getRemoteAddr() + "|" + path, path.endsWith("forgot-password") ? 5 : 20)) {
                response.setHeader("Retry-After", "60");
                SecurityConfiguration.error(response, 429, "Too many requests; try again later");
                return;
            }
            chain.doFilter(request, response);
        } catch (ServletException | IOException | RuntimeException e) { failed = true; throw e; }
        finally {
            if (path.startsWith("/api/") && (mutation || response.getStatus() >= 400 || failed)) {
                String after = actor();
                try { audit.record(after == null ? before : after, request.getRemoteAddr(), method, path,
                    failed ? 500 : response.getStatus(), (System.nanoTime() - start) / 1000000); }
                catch (RuntimeException e) {
                    // Class and SQLSTATE aid diagnosis without printing SQL values or request secrets.
                    String sqlState = "unknown";
                    Throwable cause = e;
                    for (int depth = 0; cause != null && depth < 16; depth++, cause = cause.getCause()) {
                        if (cause instanceof java.sql.SQLException sql) { sqlState = sql.getSQLState(); break; }
                    }
                    logger.error("Security audit persistence failed: type=" + e.getClass().getSimpleName()
                        + ", SQLSTATE=" + sqlState);
                }
            }
        }
    }
}
