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
    ActiveAccountFilter(UserRepository users) { this.users = users; }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        var auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth != null && auth.isAuthenticated() && !(auth instanceof AnonymousAuthenticationToken)) {
            var account = users.findByUsername(auth.getName());
            boolean active = account.filter(u -> u.isEnabled() && !u.isPasswordSetupRequired()
                    && auth.getAuthorities().stream().anyMatch(a -> a.getAuthority().equals("ROLE_" + u.getRole().name())))
                    .isPresent();
            if (!active) {
                new SecurityContextLogoutHandler().logout(request, response, auth);
                SecurityConfiguration.error(response, 401, "Authentication required");
                return;
            }
        }
        chain.doFilter(request, response);
    }
}
