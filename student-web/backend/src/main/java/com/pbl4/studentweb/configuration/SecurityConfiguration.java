package com.pbl4.studentweb.configuration;

import com.pbl4.studentweb.user.repository.UserRepository;
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
            return org.springframework.security.core.userdetails.User.withUsername(user.getUsername())
                    .password(user.getPasswordHash()).roles(user.getRole().name())
                    .disabled(!user.isEnabled() || user.isPasswordSetupRequired()).build();
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http, UserRepository users, UserAccountService accounts) throws Exception {
        // Default session-backed CSRF tokens are obtained from /api/auth/csrf and sent in the returned header.
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/auth/csrf").permitAll()
                .requestMatchers(HttpMethod.POST, "/api/auth/login", "/api/auth/activate").permitAll()
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
                .failureHandler((request, response, error) -> error(response, 401, "Invalid credentials")));
        http.logout(logout -> logout.logoutUrl("/api/auth/logout")
                .logoutSuccessHandler((request, response, auth) -> response.setStatus(204))
                .deleteCookies("JSESSIONID"));
        http.exceptionHandling(errors -> errors
                .authenticationEntryPoint((request, response, error) -> error(response, 401, "Authentication required"))
                .accessDeniedHandler((request, response, error) -> error(response, 403, "Access denied")));
        http.requestCache(cache -> cache.disable());
        http.addFilterBefore(new ActiveAccountFilter(users), AuthorizationFilter.class);
        return http.build();
    }
    static void error(HttpServletResponse response, int status, String message) throws IOException {
        response.setStatus(status);
        response.setContentType("application/json");
        response.getWriter().write("{\"status\":" + status + ",\"message\":\"" + message + "\"}");
    }
}
