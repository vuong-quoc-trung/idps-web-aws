package com.pbl4.studentweb;

import java.sql.*;
import java.util.UUID;
import org.flywaydb.core.Flyway;
import org.flywaydb.core.api.FlywayException;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import static org.assertj.core.api.Assertions.*;

/** Runs only against an explicitly supplied, disposable PostgreSQL test cluster. */
@EnabledIfEnvironmentVariable(named = "MIGRATION_TEST_URL", matches = ".+")
class FlywayMigrationTests {
    String database;
    String url;
    String user = System.getenv().getOrDefault("MIGRATION_TEST_USER", "postgres");
    String password = System.getenv().getOrDefault("MIGRATION_TEST_PASSWORD", "migration-test-only");

    @BeforeEach void createIsolatedDatabase() throws Exception {
        database = "migration_" + UUID.randomUUID().toString().replace("-", "");
        String base = System.getenv("MIGRATION_TEST_URL");
        url = base.substring(0, base.lastIndexOf('/') + 1) + database;
        try (var connection = DriverManager.getConnection(base, user, password);
             var statement = connection.createStatement()) {
            statement.execute("CREATE DATABASE " + database);
        }
    }
    @AfterEach void removeIsolatedDatabase() throws Exception {
        try (var connection = DriverManager.getConnection(System.getenv("MIGRATION_TEST_URL"), user, password);
             var statement = connection.createStatement()) {
            statement.execute("DROP DATABASE " + database + " WITH (FORCE)");
        }
    }
    Flyway flyway(boolean adopt, boolean upgrade) {
        return Flyway.configure().dataSource(url, user, password).defaultSchema("public").schemas("public")
                .locations(upgrade ? new String[]{"classpath:db/migration", "classpath:db/upgrade"}
                                   : new String[]{"classpath:db/migration"})
                .baselineVersion("1").baselineOnMigrate(adopt).cleanDisabled(true).load();
    }
    void execute(String sql) throws Exception {
        try (var connection = DriverManager.getConnection(url, user, password);
             var statement = connection.createStatement()) { statement.execute(sql); }
    }
    long count(String table) throws Exception {
        try (var connection = DriverManager.getConnection(url, user, password);
             var statement = connection.createStatement(); var result = statement.executeQuery("SELECT count(*) FROM " + table)) {
            result.next(); return result.getLong(1);
        }
    }
    @Test void freshSchemaRunsOnceAndValidatesChecksum() throws Exception {
        var migration = flyway(false, false);
        assertThat(migration.migrate().migrationsExecuted).isEqualTo(1);
        assertThat(count("students")).isZero();
        assertThat(count("admin_creation_lock")).isEqualTo(1);
        assertThat(migration.migrate().migrationsExecuted).isZero();
        migration.validate();
        execute("UPDATE flyway_schema_history SET checksum = 0 WHERE version = '1'");
        assertThatThrownBy(migration::validate).isInstanceOf(FlywayException.class);
    }
    @Test void legacySchemaRequiresExplicitAdoptionAndPreservesDataOnUpgrade() throws Exception {
        flyway(false, false).migrate();
        execute("DROP TABLE flyway_schema_history");
        execute("INSERT INTO faculties (faculty_code, faculty_name, active) VALUES ('FAC-TEST', 'Preserve me', true)");
        assertThatThrownBy(() -> flyway(false, false).migrate()).isInstanceOf(FlywayException.class);
        assertThat(flyway(true, false).migrate().migrationsExecuted).isZero();
        assertThat(count("faculties")).isEqualTo(1);
        assertThat(flyway(false, true).migrate().migrationsExecuted).isEqualTo(1);
        assertThat(count("migration_test_marker")).isZero();
        assertThat(count("faculties")).isEqualTo(1);
        assertThat(flyway(false, true).migrate().migrationsExecuted).isZero();
    }
}
