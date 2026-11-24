package com.pbl4.studentweb.configuration;

import com.pbl4.studentweb.user.repository.UserRepository;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.logout.SecurityContextLogoutHandler;
import org.springframework.web.filter.OncePerRequestFilter;

/** Recheck accounts on every request so disabling an account also revokes existing sessions. */
final class ActiveAccountFilter extends OncePerRequestFilter {
    private final UserRepository users;
    private final DevSessionLease leases;
    ActiveAccountFilter(UserRepository users, DevSessionLease leases) { this.users = users; this.leases = leases; }

    static void accountDenied(HttpServletRequest request, HttpServletResponse response, String decision) throws IOException {
        String rid = request.getHeader("X-Request-Id");
        org.slf4j.LoggerFactory.getLogger(ActiveAccountFilter.class).info(
                "BLOCK_ACCOUNT denied decision_id={} request_id={}", decision,
                rid != null && rid.matches("[a-f0-9]{32}") ? rid : "unknown");
        SecurityConfiguration.error(response, 403, "Account temporarily restricted");
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        var auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth != null && auth.isAuthenticated() && !(auth instanceof AnonymousAuthenticationToken)) {
            var account = users.findByUsername(auth.getName());
            long sessionVersion = auth.getPrincipal() instanceof AccountPrincipal p ? p.credentialVersion() : 0L;
            boolean active = account.filter(u -> u.isEnabled() && !u.isPasswordSetupRequired() && u.getCredentialVersion() == sessionVersion
                    && auth.getAuthorities().stream().anyMatch(a -> a.getAuthority().equals("ROLE_" + u.getRole().name())))
                    .isPresent();
            java.util.Optional<String> lease = java.util.Optional.empty();
            if (active && leases != null && auth.getPrincipal() instanceof AccountPrincipal actor) {
                try {
                    if (leases.temporary() && leases.eligible(actor) && "/api/auth/me".equals(request.getRequestURI()))
                        response.setHeader("X-WebSentinel-Lab-Leases", "native-v1");
                    var locked = leases.accountDecision(actor);
                    if (locked.isPresent()) {
                        accountDenied(request, response, locked.get());
                        return;
                    }
                    lease = leases.decision(actor, request.getSession(false));
                }
                catch (IOException e) {
                    SecurityConfiguration.error(response, 503, "Session check unavailable");
                    return;
                }
            }
            if (lease.isPresent() && leases.temporary()) {
                org.slf4j.LoggerFactory.getLogger(ActiveAccountFilter.class)
                        .info("BLOCK_SESSION denied decision_id={}", lease.get());
                SecurityConfiguration.error(response, 403, "Session temporarily restricted");
                return;
            }
            if (lease.isPresent()) org.slf4j.LoggerFactory.getLogger(ActiveAccountFilter.class)
                .info("Development session revocation decision_id={}", lease.get());
            if (!active || lease.isPresent()) {
                var signals = com.pbl4.studentweb.accesslog.service.SecuritySignals.get(request);
                signals.mark(com.pbl4.studentweb.accesslog.service.SecuritySignals.Reason.SESSION_REVOKED);
                if (account.filter(u -> !u.isEnabled() || u.isPasswordSetupRequired()).isPresent()
                        && !java.util.Set.of("GET", "HEAD", "OPTIONS").contains(request.getMethod()))
                    signals.mark(com.pbl4.studentweb.accesslog.service.SecuritySignals.Reason.WORKFLOW_DENIED);
                new SecurityContextLogoutHandler().logout(request, response, auth);
                SecurityConfiguration.error(response, 401, "Authentication required");
                return;
            }
        }
        chain.doFilter(request, response);
    }
}
