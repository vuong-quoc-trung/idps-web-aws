package com.pbl4.studentweb.configuration;

import com.pbl4.studentweb.accesslog.service.AccessLogRetentionService;
import java.time.LocalDateTime;
import lombok.RequiredArgsConstructor;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;

@Configuration
@EnableScheduling
@RequiredArgsConstructor
@ConditionalOnProperty(name = "app.audit.retention.enabled", havingValue = "true", matchIfMissing = true)
public class AccessLogRetentionConfiguration {
    private final AccessLogRetentionService retention;

    @Scheduled(initialDelayString = "${app.audit.retention.initial-delay-ms:60000}",
               fixedDelayString = "${app.audit.retention.interval-ms:600000}")
    public void cleanExpiredLogs() {
        var cutoff = LocalDateTime.now().minusDays(3);
        int total = 0;
        for (int batch = 0; batch < 20; batch++) {
            int deleted = retention.deleteBatch(cutoff);
            total += deleted;
            if (deleted < AccessLogRetentionService.BATCH_SIZE) break;
        }
        if (total > 0) org.slf4j.LoggerFactory.getLogger(getClass()).info("Deleted {} audit logs older than 3 days", total);
    }
}
