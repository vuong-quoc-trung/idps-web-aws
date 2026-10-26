package com.pbl4.studentweb.configuration;

import jakarta.servlet.http.HttpServletRequest;
import java.net.InetAddress;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/** Resolves client metadata without DNS or trusting headers from arbitrary peers. */
@Component
public final class RequestAttribution {
    private static final int MAX_HOPS = 16;
    private static final int MAX_HEADER_BYTES = 2048;
    private final List<Network> trusted;

    public RequestAttribution(@Value("${app.security.trusted-proxies:}") String proxies,
            @Value("${server.forward-headers-strategy:NONE}") String forwardingStrategy) {
        // Otherwise getRemoteAddr() may already have been rewritten before our trust check.
        if (!"NONE".equalsIgnoreCase(forwardingStrategy))
            throw new IllegalArgumentException("Student audit requires server.forward-headers-strategy=NONE");
        var networks = new ArrayList<Network>();
        if (!proxies.isBlank()) {
            for (String value : proxies.split(",", -1)) networks.add(Network.parse(value.trim()));
        }
        trusted = List.copyOf(networks);
    }

    public record Identity(String clientIp, String peerIp, String requestId) {}

    public Identity resolve(HttpServletRequest request) {
        if (request.getAttribute(TrustedForwardingConfiguration.IDENTITY_ATTRIBUTE) instanceof Identity identity) return identity;
        InetAddress peer = literal(request.getRemoteAddr());
        InetAddress client = peer;
        boolean trustedPeer = isTrusted(peer);
        if (trustedPeer) {
            List<InetAddress> chain = forwardedChain(request);
            if (chain != null) {
                for (int i = chain.size() - 1; i >= 0 && isTrusted(client); i--) client = chain.get(i);
            } else if (request.getHeader("X-Forwarded-For") == null) {
                // An invalid XFF never falls back to another potentially conflicting header.
                String real = singleHeader(request, "X-Real-IP");
                InetAddress candidate = literal(real);
                if (candidate != null) client = candidate;
            }
        }
        String supplied = trustedPeer ? singleHeader(request, "X-Request-ID") : null;
        String requestId = validRequestId(supplied) ? supplied : UUID.randomUUID().toString();
        return new Identity(address(client), address(peer), requestId);
    }

    public static boolean validRequestId(String value) {
        return value != null && value.length() <= 128 && value.matches("[A-Za-z0-9._:-]{1,128}");
    }

    private static String singleHeader(HttpServletRequest request, String name) {
        var values = request.getHeaders(name);
        if (values == null || !values.hasMoreElements()) return null;
        String value = values.nextElement();
        return values.hasMoreElements() ? null : value;
    }

    private static List<InetAddress> forwardedChain(HttpServletRequest request) {
        var values = request.getHeaders("X-Forwarded-For");
        if (values == null || !values.hasMoreElements()) return null;
        var chain = new ArrayList<InetAddress>();
        int total = 0;
        while (values.hasMoreElements()) {
            String value = values.nextElement();
            total += value.length();
            if (total > MAX_HEADER_BYTES) return null;
            for (String hop : value.split(",", -1)) {
                InetAddress ip = literal(hop);
                if (ip == null || chain.size() >= MAX_HOPS) return null;
                chain.add(ip);
            }
        }
        return chain.isEmpty() ? null : chain;
    }

    public boolean isTrustedPeer(String peer) { return isTrusted(literal(peer)); }

    private boolean isTrusted(InetAddress address) {
        return address != null && trusted.stream().anyMatch(network -> network.contains(address));
    }

    private static String address(InetAddress value) { return value == null ? null : value.getHostAddress(); }

    static InetAddress literal(String raw) {
        if (raw == null) return null;
        String value = raw.trim();
        if (value.isEmpty() || value.length() > 64 || value.indexOf('%') >= 0 || value.indexOf('/') >= 0)
            return null;
        // Reject IPv4 shorthand/hex/octal and names before calling the literal-only JDK API.
        if (value.indexOf(':') < 0 && !value.matches("(?:0|[1-9][0-9]{0,2})(?:\\.(?:0|[1-9][0-9]{0,2})){3}"))
            return null;
        try { return InetAddress.ofLiteral(value); }
        catch (IllegalArgumentException e) { return null; }
    }

    private record Network(byte[] address, int prefix) {
        static Network parse(String value) {
            String[] parts = value.split("/", -1);
            InetAddress ip = literal(parts[0]);
            if (parts.length > 2 || ip == null)
                throw new IllegalArgumentException("Trusted proxies must contain literal IPs or CIDRs");
            byte[] bytes = ip.getAddress();
            int prefix = bytes.length * 8;
            if (parts.length == 2) {
                try {
                    if (!parts[1].matches("[0-9]{1,3}")) throw new NumberFormatException();
                    prefix = Integer.parseInt(parts[1]);
                    // The JDK normalizes IPv4-mapped IPv6 literals to IPv4 addresses.
                    if (bytes.length == 4 && parts[0].contains(":") && prefix >= 96) prefix -= 96;
                } catch (NumberFormatException e) {
                    throw new IllegalArgumentException("Trusted proxy CIDR prefix is invalid");
                }
                if (prefix < 0 || prefix > bytes.length * 8)
                    throw new IllegalArgumentException("Trusted proxy CIDR prefix is invalid");
            }
            return new Network(bytes, prefix);
        }
        boolean contains(InetAddress ip) {
            byte[] candidate = ip.getAddress();
            if (candidate.length != address.length) return false;
            for (int bit = 0; bit < prefix; bit++) {
                int mask = 1 << (7 - bit % 8);
                if ((candidate[bit / 8] & mask) != (address[bit / 8] & mask)) return false;
            }
            return true;
        }
    }
}
