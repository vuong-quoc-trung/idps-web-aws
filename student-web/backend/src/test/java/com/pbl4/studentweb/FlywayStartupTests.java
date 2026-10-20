package com.pbl4.studentweb;

import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import static org.assertj.core.api.Assertions.*;

/** MIGRATION_TEST_URL must point to an empty, disposable PostgreSQL database. */
@EnabledIfEnvironmentVariable(named = "MIGRATION_TEST_URL", matches = ".+")
@SpringBootTest(properties = {
    "spring.flyway.enabled=true", "spring.flyway.baseline-on-migrate=false",
    "spring.jpa.hibernate.ddl-auto=validate", "app.bootstrap.enabled=false",
    "app.audit.retention.enabled=false", "logging.level.root=WARN"
})
class FlywayStartupTests {
    @DynamicPropertySource static void postgres(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", () -> System.getenv("MIGRATION_TEST_URL"));
        registry.add("spring.datasource.username", () -> System.getenv().getOrDefault("MIGRATION_TEST_USER", "postgres"));
        registry.add("spring.datasource.password", () -> System.getenv().getOrDefault("MIGRATION_TEST_PASSWORD", "migration-test-only"));
    }
    @Autowired Flyway flyway;
    @Test void flywayRunsBeforeHibernateSchemaValidation() {
        assertThat(flyway.info().current().getVersion().toString()).isEqualTo("1");
        assertThat(flyway.info().pending()).isEmpty();
        flyway.validate();
    }
}
