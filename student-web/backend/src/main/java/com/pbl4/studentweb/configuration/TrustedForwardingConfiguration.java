package com.pbl4.studentweb.configuration;

import jakarta.servlet.*;
import jakarta.servlet.http.*;
import java.io.IOException;
import java.util.*;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.*;
import org.springframework.core.Ordered;
import org.springframework.web.filter.ForwardedHeaderFilter;

/** Only sanitized, trust-checked forwarding metadata reaches Spring's forwarding filter. */
@Configuration
public class TrustedForwardingConfiguration {
    public static final String IDENTITY_ATTRIBUTE = TrustedForwardingConfiguration.class.getName() + ".identity";
    @Bean FilterRegistrationBean<ForwardedHeaderFilter> trustedForwardedHeaders(RequestAttribution attribution) {
        var filter = new ForwardedHeaderFilter() {
            @Override protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
                    throws ServletException, IOException {
                var identity = attribution.resolve(request);
                request.setAttribute(IDENTITY_ATTRIBUTE, identity);
                var sanitized = new HttpServletRequestWrapper(request) {
                    @Override public String getHeader(String name) {
                        String lower = name.toLowerCase(Locale.ROOT);
                        if (lower.equals("x-forwarded-for")) return identity.clientIp();
                        if (lower.equals("x-forwarded-proto") && attribution.isTrustedPeer(identity.peerIp())) {
                            String scheme = super.getHeader(name);
                            return "http".equals(scheme) || "https".equals(scheme) ? scheme : null;
                        }
                        if (lower.equals("forwarded") || lower.startsWith("x-forwarded-") || lower.equals("x-real-ip")) return null;
                        return super.getHeader(name);
                    }
                    @Override public Enumeration<String> getHeaders(String name) {
                        String value = getHeader(name);
                        return value == null ? Collections.emptyEnumeration() : Collections.enumeration(List.of(value));
                    }
                    @Override public Enumeration<String> getHeaderNames() {
                        var names = new HashSet<String>(Collections.list(super.getHeaderNames()));
                        names.removeIf(n -> n.equalsIgnoreCase("Forwarded") || n.toLowerCase(Locale.ROOT).startsWith("x-forwarded-") || n.equalsIgnoreCase("X-Real-IP"));
                        names.add("X-Forwarded-For"); names.add("X-Forwarded-Proto");
                        return Collections.enumeration(names);
                    }
                };
                super.doFilterInternal(sanitized, response, chain);
            }
        };
        var registration = new FilterRegistrationBean<ForwardedHeaderFilter>(filter);
        registration.setName("trustedForwardedHeaders");
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);
        registration.setDispatcherTypes(DispatcherType.REQUEST, DispatcherType.ASYNC, DispatcherType.ERROR);
        return registration;
    }
}
