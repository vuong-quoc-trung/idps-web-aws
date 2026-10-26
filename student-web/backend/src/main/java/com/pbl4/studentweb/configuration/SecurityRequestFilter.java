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
                response.setHeader("Retry-After", "60");
                SecurityConfiguration.error(response, 429, "Too many requests; try again later");
                return;
            }
            chain.doFilter(request, response);
        } catch (ServletException | IOException | RuntimeException e) { failed = true; throw e; }
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
                    failed ? 500 : response.getStatus(), (System.nanoTime() - start) / 1000000, request.getHeader("User-Agent"), false));
            }
        }
    }
}
