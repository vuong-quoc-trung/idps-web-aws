package com.pbl4.studentweb.configuration;

import com.pbl4.studentweb.accesslog.service.SecurityAuditService;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.*;
import java.time.*;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

class SecurityRequestFilterTests {
    @Test void blocksExcessiveRequestsAndAuditsWithoutSecrets() throws Exception {
        var audit = mock(SecurityAuditService.class);
        var filter = new SecurityRequestFilter(new SensitiveRequestLimiter(), audit, new RequestAttribution("", "NONE"), true);
        for (int i = 0; i < 21; i++) {
            var request = new MockHttpServletRequest("POST", "/api/auth/login");
            request.setRemoteAddr("192.0.2.1");
            request.addParameter("password", "secret-not-for-audit");
            var response = new MockHttpServletResponse();
            filter.doFilter(request, response, (req, res) -> ((jakarta.servlet.http.HttpServletResponse) res).setStatus(401));
            assertThat(response.getStatus()).isEqualTo(i == 20 ? 429 : 401);
            if (i == 20) assertThat(response.getHeader("Retry-After")).isEqualTo("60");
        }
        verify(audit).record(argThat(e -> e.statusCode() == 429 && "192.0.2.1".equals(e.clientIp()) && e.queryString() == null));
    }
    @Test void windowExpiresAndClientsAreIndependent() {
        Clock clock = mock(Clock.class);
        when(clock.millis()).thenReturn(0L);
        var limiter = new SensitiveRequestLimiter(clock);
        assertThat(limiter.allow("one", 1)).isTrue();
        assertThat(limiter.allow("one", 1)).isFalse();
        assertThat(limiter.allow("two", 1)).isTrue();
        when(clock.millis()).thenReturn(60000L);
        assertThat(limiter.allow("one", 1)).isTrue();
    }

    @Test void readsCanBeCapturedOrDisabledAndHeadersAreRecorded() throws Exception {
        for (boolean includeReads : new boolean[]{true, false}) {
            for (String method : new String[]{"GET", "HEAD", "OPTIONS"}) {
                var audit = mock(SecurityAuditService.class);
                var filter = new SecurityRequestFilter(new SensitiveRequestLimiter(), audit, new RequestAttribution("127.0.0.1", "NONE"), includeReads);
                var request = new MockHttpServletRequest(method, "/api/auth/me");
                request.setRemoteAddr("127.0.0.1"); request.addHeader("X-Forwarded-For", "192.0.2.3");
                request.addHeader("X-Request-Id", "edge-456"); request.addHeader("User-Agent", "Mozilla/5.0 UnitTest");
                var response = new MockHttpServletResponse();
                filter.doFilter(request, response, (req, res) -> ((jakarta.servlet.http.HttpServletResponse)res).setStatus(204));
                assertThat(response.getHeader("X-Request-Id")).isEqualTo("edge-456");
                if (includeReads) verify(audit).record(argThat(e -> "192.0.2.3".equals(e.clientIp()) && "edge-456".equals(e.requestId()) && "Mozilla".equals(e.userAgent()) && e.timestamp()!=null));
                else verifyNoInteractions(audit);
            }
        }
    }
}
