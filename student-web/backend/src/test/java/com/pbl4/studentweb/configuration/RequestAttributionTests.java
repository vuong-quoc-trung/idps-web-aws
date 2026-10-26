package com.pbl4.studentweb.configuration;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.*;
import static org.assertj.core.api.Assertions.*;

class RequestAttributionTests {
    private MockHttpServletRequest request(String peer, String forwarded) {
        var request = new MockHttpServletRequest("GET", "/api/auth/me");
        request.setRemoteAddr(peer);
        if (forwarded != null) request.addHeader("X-Forwarded-For", forwarded);
        request.addHeader("X-Request-Id", "edge-123");
        return request;
    }
    @Test void untrustedPeerCannotSpoofClientOrCorrelation() {
        var identity = new RequestAttribution("127.0.0.1/32", "NONE").resolve(request("192.0.2.1", "203.0.113.99"));
        assertThat(identity.clientIp()).isEqualTo("192.0.2.1");
        assertThat(identity.requestId()).isNotEqualTo("edge-123");
    }
    @Test void walksFromTrustedEdgeAndStopsAtFirstUntrustedHop() {
        var resolver = new RequestAttribution("127.0.0.1/32,10.0.0.0/8", "NONE");
        var identity = resolver.resolve(request("127.0.0.1", "203.0.113.99,192.0.2.1,10.0.0.2"));
        assertThat(identity.clientIp()).isEqualTo("192.0.2.1");
        assertThat(identity.peerIp()).isEqualTo("127.0.0.1");
        assertThat(identity.requestId()).isEqualTo("edge-123");
    }
    @Test void invalidOrOversizedChainsFailClosedAndRealIpIsOnlyFallback() {
        var resolver = new RequestAttribution("127.0.0.1,::1", "NONE");
        for (String value : new String[]{"unknown", "localhost", "192.0.2.1,", "192.0.2.1,".repeat(20)}) {
            var request = request("127.0.0.1", value);
            request.addHeader("X-Real-IP", "203.0.113.99");
            assertThat(resolver.resolve(request).clientIp()).isEqualTo("127.0.0.1");
        }
        var request = request("127.0.0.1", null);
        request.addHeader("X-Real-IP", "2001:db8::1");
        assertThat(resolver.resolve(request).clientIp()).contains("2001:db8:");
        assertThat(resolver.resolve(request("::1", "2001:db8::2")).clientIp()).contains("2001:db8:");
        assertThatThrownBy(() -> new RequestAttribution("localhost", "NONE")).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new RequestAttribution("10.0.0.0/33", "NONE")).isInstanceOf(IllegalArgumentException.class);
    }
    @Test void requestIdIsBoundedAndServletFilterUsesOnlyVerifiedAddress() throws Exception {
        var resolver = new RequestAttribution("127.0.0.1", "NONE");
        var request = request("127.0.0.1", "192.0.2.1");
        request.addHeader("Forwarded", "for=203.0.113.99;proto=https;host=evil.invalid");
        request.addHeader("X-Forwarded-Host", "evil.invalid");
        var filter = new TrustedForwardingConfiguration().trustedForwardedHeaders(resolver).getFilter();
        filter.doFilter(request, new MockHttpServletResponse(), (req, res) -> {
            assertThat(req.getRemoteAddr()).isEqualTo("192.0.2.1");
            assertThat(resolver.resolve((jakarta.servlet.http.HttpServletRequest)req).peerIp()).isEqualTo("127.0.0.1");
            assertThat(((jakarta.servlet.http.HttpServletRequest)req).getServerName()).isNotEqualTo("evil.invalid");
        });
        assertThat(RequestAttribution.validRequestId("a".repeat(129))).isFalse();
        assertThat(RequestAttribution.validRequestId("bad\r\nID")).isFalse();
    }
}
