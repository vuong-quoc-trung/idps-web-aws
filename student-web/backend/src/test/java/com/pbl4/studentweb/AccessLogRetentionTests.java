package com.pbl4.studentweb;

import com.pbl4.studentweb.accesslog.entity.AccessLog;
import com.pbl4.studentweb.accesslog.repository.AccessLogRepository;
import com.pbl4.studentweb.accesslog.service.AccessLogRetentionService;
import java.time.LocalDateTime;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;
import static org.assertj.core.api.Assertions.*;

@SpringBootTest(properties = {
    "spring.datasource.url=jdbc:h2:mem:retention;MODE=PostgreSQL;DB_CLOSE_DELAY=-1",
    "spring.datasource.username=sa", "spring.datasource.password=",
    "spring.jpa.hibernate.ddl-auto=create-drop", "spring.jpa.properties.hibernate.default_schema=PUBLIC",
    "app.bootstrap.enabled=false", "app.audit.retention.enabled=false", "logging.level.root=WARN"
})
@Transactional
class AccessLogRetentionTests {
    @Autowired AccessLogRepository repository;
    @Autowired AccessLogRetentionService retention;
    @Autowired JdbcTemplate jdbc;

    private long logAt(LocalDateTime date) {
        var log = new AccessLog(); log.setHttpMethod("PUT"); log.setRequestPath("/api/me/profile");
        long id = repository.saveAndFlush(log).getId();
        jdbc.update("update access_logs set created_at = ? where id = ?", date, id);
        return id;
    }
    @Test void removesOnlyOlderRowsInBoundedBatches() {
        var cutoff = LocalDateTime.of(2026, 10, 15, 12, 0);
        long boundary = logAt(cutoff), recent = logAt(cutoff.plusHours(1));
        for (int i = 0; i < 501; i++) logAt(cutoff.minusSeconds(i + 1));
        assertThat(retention.deleteBatch(cutoff)).isEqualTo(500);
        assertThat(repository.count()).isEqualTo(3);
        assertThat(retention.deleteBatch(cutoff)).isEqualTo(1);
        assertThat(retention.deleteBatch(cutoff)).isZero();
        assertThat(repository.existsById(boundary)).isTrue();
        assertThat(repository.existsById(recent)).isTrue();
    }
}
