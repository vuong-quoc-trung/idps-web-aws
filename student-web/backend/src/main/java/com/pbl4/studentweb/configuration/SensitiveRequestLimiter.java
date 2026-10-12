package com.pbl4.studentweb.configuration;

import java.time.Clock;
import java.util.HashMap;
import java.util.Map;
import org.springframework.stereotype.Component;

/** Bounded per-process limiter. A shared gateway limiter is required for multiple replicas. */
@Component
public class SensitiveRequestLimiter {
    private record Window(long start, int count) {}
    private final Map<String, Window> windows = new HashMap<>();
    @org.springframework.beans.factory.annotation.Value("${app.security.rate-limit-enabled:true}")
    private boolean enabled = true;
    private final Clock clock;
    public SensitiveRequestLimiter() { this(Clock.systemUTC()); }
    SensitiveRequestLimiter(Clock clock) { this.clock = clock; }
    public synchronized boolean allow(String key, int limit) {
        if (!enabled) return true;
        long now = clock.millis();
        windows.entrySet().removeIf(e -> now - e.getValue().start() >= 60000);
        var window = windows.get(key);
        if (window == null) {
            if (windows.size() >= 10000) return false;
            windows.put(key, new Window(now, 1)); return true;
        }
        if (window.count() >= limit) return false;
        windows.put(key, new Window(window.start(), window.count() + 1)); return true;
    }
}
