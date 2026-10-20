package com.pbl4.studentweb;

import com.pbl4.studentweb.user.dto.CreateUserRequest;
import com.pbl4.studentweb.user.entity.UserRole;
import com.pbl4.studentweb.user.repository.UserRepository;
import com.pbl4.studentweb.user.service.PasswordSetupService;
import com.pbl4.studentweb.user.service.UserAccountService;
import java.util.ArrayList;
import java.util.concurrent.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import static org.assertj.core.api.Assertions.*;

/** Real commits and independent connections; deliberately NOT @Transactional. Test database only. */
@EnabledIfEnvironmentVariable(named = "MIGRATION_TEST_URL", matches = ".+")
@SpringBootTest(properties = {
    "spring.flyway.enabled=true", "spring.flyway.baseline-on-migrate=false",
    "spring.jpa.hibernate.ddl-auto=validate", "app.bootstrap.enabled=false",
    "app.audit.retention.enabled=false", "logging.level.root=WARN",
    "spring.datasource.hikari.connection-init-sql=SET statement_timeout = '15s'"
})
class PostgresAccountTransactionTests {
    @DynamicPropertySource static void postgres(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", () -> System.getenv("MIGRATION_TEST_URL"));
        registry.add("spring.datasource.username", () -> System.getenv().getOrDefault("MIGRATION_TEST_USER", "postgres"));
        registry.add("spring.datasource.password", () -> System.getenv().getOrDefault("MIGRATION_TEST_PASSWORD", "migration-test-only"));
    }
    @Autowired UserAccountService accounts;
    @Autowired PasswordSetupService passwords;
    @Autowired UserRepository users;
    @Autowired PasswordEncoder encoder;
    @Autowired PlatformTransactionManager manager;
    @Autowired JdbcTemplate jdbc;
    private static final String PREFIX = "pg-transaction-";
    private static final String PASSWORD = "Postgres-test-password-123";

    @AfterEach void cleanFixtures() {
        // Only fixtures owned by this suite, never TRUNCATE shared tables.
        jdbc.update("DELETE FROM public.users WHERE username LIKE ?", PREFIX + "%");
    }
    @Test void concurrentAdminCreationNeverExceedsThreeIncludingDisabledAccounts() throws Exception {
        assertThat(users.countByRole(UserRole.ADMIN)).as("Requires a dedicated empty test database").isZero();
        var first = accounts.create(new CreateUserRequest(PREFIX + "admin-one", UserRole.ADMIN));
        accounts.create(new CreateUserRequest(PREFIX + "admin-two", UserRole.ADMIN));
        accounts.setEnabled(first.user().id(), false, -1L);
        var ready = new CountDownLatch(3);
        var start = new CountDownLatch(1);
        try (var pool = Executors.newFixedThreadPool(3)) {
            var results = new ArrayList<Future<Boolean>>();
            for (int i = 0; i < 3; i++) {
                String name = PREFIX + "admin-race-" + i;
                results.add(pool.submit(() -> {
                    ready.countDown();
                    if (!start.await(10, TimeUnit.SECONDS)) throw new AssertionError("Start timeout");
                    try { accounts.create(new CreateUserRequest(name, UserRole.ADMIN)); return true; }
                    catch (IllegalStateException e) {
                        assertThat(e.getMessage()).contains("tối đa 3"); return false;
                    }
                }));
            }
            assertThat(ready.await(10, TimeUnit.SECONDS)).isTrue();
            start.countDown();
            int successes = 0;
            for (var future : results) if (future.get(30, TimeUnit.SECONDS)) successes++;
            assertThat(successes).isEqualTo(1);
        }
        assertThat(users.countByRole(UserRole.ADMIN)).isEqualTo(3);
        assertThatThrownBy(() -> accounts.create(new CreateUserRequest(PREFIX + "fourth", UserRole.ADMIN)))
                .isInstanceOf(IllegalStateException.class).hasMessageContaining("tối đa 3");
        assertThat(users.existsByUsername(PREFIX + "fourth")).isFalse();
        accounts.create(new CreateUserRequest(PREFIX + "staff", UserRole.STAFF));
    }
    @Test void concurrentActivationConsumesTokenExactlyOnce() throws Exception {
        var created = accounts.create(new CreateUserRequest(PREFIX + "activation", UserRole.STAFF));
        var ready = new CountDownLatch(2);
        var start = new CountDownLatch(1);
        try (var pool = Executors.newFixedThreadPool(2)) {
            var results = new ArrayList<Future<Integer>>();
            for (int i = 0; i < 2; i++) {
                int attempt = i;
                results.add(pool.submit(() -> {
                    ready.countDown();
                    if (!start.await(10, TimeUnit.SECONDS)) throw new AssertionError("Start timeout");
                    try { passwords.setInitialPassword(created.activationToken(), PASSWORD + attempt); return attempt; }
                    catch (IllegalArgumentException e) {
                        assertThat(e.getMessage()).contains("activation token"); return -1;
                    }
                }));
            }
            assertThat(ready.await(10, TimeUnit.SECONDS)).isTrue();
            start.countDown();
            var winners = new ArrayList<Integer>();
            for (var future : results) { int result = future.get(30, TimeUnit.SECONDS); if (result >= 0) winners.add(result); }
            assertThat(winners).hasSize(1);
            var saved = users.findById(created.user().id()).orElseThrow();
            assertThat(saved.isPasswordSetupRequired()).isFalse();
            assertThat(saved.getActivationTokenHash()).isNull();
            assertThat(saved.getActivationExpiresAt()).isNull();
            assertThat(encoder.matches(PASSWORD + winners.getFirst(), saved.getPasswordHash())).isTrue();
        }
        assertThatThrownBy(() -> passwords.setInitialPassword(created.activationToken(), PASSWORD))
                .isInstanceOf(IllegalArgumentException.class);
    }
    @Test void rollbackUndoesAccountCreationAndTokenConsumption() {
        var tx = new TransactionTemplate(manager);
        assertThatThrownBy(() -> tx.executeWithoutResult(status -> {
            accounts.create(new CreateUserRequest(PREFIX + "rollback-create", UserRole.STAFF));
            throw new IllegalStateException("Force rollback");
        })).isInstanceOf(IllegalStateException.class).hasMessage("Force rollback");
        assertThat(users.existsByUsername(PREFIX + "rollback-create")).isFalse();
        var created = accounts.create(new CreateUserRequest(PREFIX + "rollback-token", UserRole.STAFF));
        var before = users.findById(created.user().id()).orElseThrow();
        assertThatThrownBy(() -> tx.executeWithoutResult(status -> {
            passwords.setInitialPassword(created.activationToken(), PASSWORD);
            users.flush(); // Force SQL before rollback, rather than only changing managed objects.
            throw new IllegalStateException("Force rollback");
        })).isInstanceOf(IllegalStateException.class).hasMessage("Force rollback");
        var after = users.findById(created.user().id()).orElseThrow();
        assertThat(after.isPasswordSetupRequired()).isTrue();
        assertThat(after.getPasswordHash()).isEqualTo(before.getPasswordHash());
        assertThat(after.getActivationTokenHash()).isEqualTo(before.getActivationTokenHash());
        passwords.setInitialPassword(created.activationToken(), PASSWORD);
        assertThat(users.findById(created.user().id()).orElseThrow().isPasswordSetupRequired()).isFalse();
    }
    @Test void pessimisticLockBlocksSecondTransactionUntilCommit() throws Exception {
        var created = accounts.create(new CreateUserRequest(PREFIX + "lock", UserRole.STAFF));
        var tx = new TransactionTemplate(manager);
        var waiterPid = new CompletableFuture<Integer>();
        try (var pool = Executors.newSingleThreadExecutor()) {
            Future<?> waiter = tx.execute(status -> {
                users.findForUpdate(created.user().id()).orElseThrow();
                var future = pool.submit(() -> tx.executeWithoutResult(other -> {
                    waiterPid.complete(jdbc.queryForObject("SELECT pg_backend_pid()", Integer.class));
                    users.findForUpdate(created.user().id()).orElseThrow().setEnabled(false);
                }));
                try {
                    int pid = waiterPid.get(10, TimeUnit.SECONDS);
                    long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
                    boolean waiting = false;
                    while (System.nanoTime() < deadline) {
                        waiting = Boolean.TRUE.equals(jdbc.queryForObject(
                            "SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE pid = ? AND wait_event_type = 'Lock')",
                            Boolean.class, pid));
                        if (waiting) break;
                        Thread.sleep(25);
                    }
                    assertThat(waiting).as("PostgreSQL reports the second connection waiting on a lock").isTrue();
                    assertThat(future.isDone()).isFalse();
                } catch (Exception e) { throw new AssertionError(e); }
                return future;
            }); // Commit releases the row lock.
            waiter.get(30, TimeUnit.SECONDS);
        }
        assertThat(users.findById(created.user().id()).orElseThrow().isEnabled()).isFalse();
    }
}
