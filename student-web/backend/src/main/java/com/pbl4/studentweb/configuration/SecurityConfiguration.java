package com.pbl4.studentweb.configuration;

import com.pbl4.studentweb.user.repository.UserRepository;
import com.pbl4.studentweb.accesslog.service.SecuritySignals;
import com.pbl4.studentweb.user.service.UserAccountService;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;

@Configuration
public class SecurityConfiguration {
    @Bean
    UserDetailsService userDetailsService(UserRepository users) {
        return username -> {
            var user = users.findByUsername(username).orElseThrow(() -> new UsernameNotFoundException("Invalid credentials"));
            return new AccountPrincipal(user);
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http, UserRepository users, UserAccountService accounts, SensitiveRequestLimiter limiter,
            com.pbl4.studentweb.accesslog.service.SecurityAuditService audit, RequestAttribution attribution,
            @org.springframework.beans.factory.annotation.Value("${app.audit.include-successful-reads:true}") boolean includeReads) throws Exception {
        // Default session-backed CSRF tokens are obtained from /api/auth/csrf and sent in the returned header.
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/auth/csrf").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/profile-options").authenticated()
                .requestMatchers(HttpMethod.POST, "/api/auth/login", "/api/auth/activate", "/api/auth/activation/verify", "/api/auth/activation/send", "/api/auth/forgot-password", "/api/auth/reset-password").permitAll()
                .requestMatchers(HttpMethod.POST, "/api/auth/change-password").hasAnyRole("STUDENT", "ADMIN", "STAFF")
                .requestMatchers("/api/auth/me", "/api/auth/logout").authenticated()
                .requestMatchers("/api/users/**", "/api/access-logs/**").hasRole("ADMIN")
                .requestMatchers("/api/students/**").hasAnyRole("ADMIN", "STAFF")
                .requestMatchers("/api/me/**").hasRole("STUDENT")
                .requestMatchers(HttpMethod.GET, "/api/faculties/**", "/api/majors/**", "/api/classes/**", "/api/training-programs/**").authenticated()
                .requestMatchers("/api/faculties/**", "/api/majors/**", "/api/classes/**", "/api/training-programs/**").hasAnyRole("ADMIN", "STAFF")
                .anyRequest().denyAll());
        http.formLogin(form -> form.loginProcessingUrl("/api/auth/login")
                .successHandler((request, response, auth) -> {
                    accounts.recordLogin(auth.getName());
                    response.setStatus(204);
                })
                .failureHandler((request, response, error) -> {
                    SecuritySignals.get(request).loginFailed(request.getParameter("username"));
                    error(response, 401, "Invalid credentials");
                }));
        http.logout(logout -> logout.logoutUrl("/api/auth/logout")
                .logoutSuccessHandler((request, response, auth) -> response.setStatus(204))
                .deleteCookies("JSESSIONID"));
        http.exceptionHandling(errors -> errors
                .authenticationEntryPoint((request, response, error) -> {
                    decisionMetadata(request, response, 401);
                    if (request.getRequestedSessionId() != null && !request.isRequestedSessionIdValid())
                        SecuritySignals.get(request).mark(SecuritySignals.Reason.INVALID_SESSION);
                    error(response, 401, "Authentication required");
                })
                .accessDeniedHandler((request, response, error) -> {
                    decisionMetadata(request, response, 403);
                    if (error instanceof org.springframework.security.web.csrf.CsrfException)
                        SecuritySignals.get(request).mark(SecuritySignals.Reason.CSRF_INVALID);
                    // Exclude CSRF failures: they do not establish lack of privilege.
                    String path = request.getRequestURI().substring(request.getContextPath().length());
                    if (!(error instanceof org.springframework.security.web.csrf.CsrfException)
                            && !java.util.Set.of("GET", "HEAD", "OPTIONS").contains(request.getMethod())
                            && (path.equals("/api/users") || path.matches("/api/users/[0-9]+/(enabled|activation-token)")))
                        SecuritySignals.get(request).mark(SecuritySignals.Reason.PRIVILEGE_DENIED);
                    error(response, 403, "Access denied");
                }));
        http.addFilterBefore(new SecurityRequestFilter(limiter, audit, attribution, includeReads), org.springframework.security.web.csrf.CsrfFilter.class);
        http.sessionManagement(session -> session.sessionFixation(fixation -> fixation.changeSessionId()));
        http.headers(headers -> headers.contentSecurityPolicy(csp -> csp.policyDirectives("default-src 'none'; frame-ancestors 'none'")));
        http.requestCache(cache -> cache.disable());
        http.addFilterBefore(new ActiveAccountFilter(users), AuthorizationFilter.class);
        return http.build();
    }
    private static void decisionMetadata(jakarta.servlet.http.HttpServletRequest request, HttpServletResponse response, int status) {
        Object errorStatus = request.getAttribute(jakarta.servlet.RequestDispatcher.ERROR_STATUS_CODE);
        org.slf4j.LoggerFactory.getLogger(SecurityConfiguration.class).debug(
                "Security decision: dispatch={}, error_status={}, request_id={}, status={}",
                request.getDispatcherType(), errorStatus instanceof Integer ? errorStatus : null,
                response.getHeader("X-Request-Id"), status);
    }
    static void error(HttpServletResponse response, int status, String message) throws IOException {
        response.setStatus(status);
        response.setContentType("application/json");
        response.getWriter().write("{\"status\":" + status + ",\"message\":\"" + message + "\"}");
    }
}
