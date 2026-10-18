package com.pbl4.studentweb;

import com.pbl4.studentweb.user.dto.CreateUserRequest;
import com.pbl4.studentweb.user.entity.UserRole;
import com.pbl4.studentweb.user.repository.UserRepository;
import com.pbl4.studentweb.user.service.UserAccountService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import java.util.concurrent.*;
import static org.assertj.core.api.Assertions.*;

@SpringBootTest(properties = {
    "spring.datasource.url=jdbc:h2:mem:adminlimit;MODE=PostgreSQL;DB_CLOSE_DELAY=-1;LOCK_TIMEOUT=10000",
    "spring.datasource.username=sa", "spring.datasource.password=",
    "spring.jpa.hibernate.ddl-auto=create-drop", "spring.jpa.properties.hibernate.default_schema=PUBLIC",
    "app.bootstrap.enabled=false", "app.audit.retention.enabled=false", "logging.level.root=WARN"
})
class AdminLimitTests {
    @Autowired UserAccountService service;
    @Autowired UserRepository users;
    @Test void concurrentCreatesCannotExceedThreeAndDisabledAdminsStillCount() throws Exception {
        var first = service.create(new CreateUserRequest("admin-one", UserRole.ADMIN));
        service.create(new CreateUserRequest("admin-two", UserRole.ADMIN));
        var disabled = users.findById(first.user().id()).orElseThrow();
        disabled.setEnabled(false); users.saveAndFlush(disabled);
        var start = new CountDownLatch(1);
        try (var pool = Executors.newFixedThreadPool(3)) {
            var results = new java.util.ArrayList<Future<Boolean>>();
            for (int i = 0; i < 3; i++) {
                final String name = "concurrent-admin-" + i;
                results.add(pool.submit(() -> {
                    start.await();
                    try { service.create(new CreateUserRequest(name, UserRole.ADMIN)); return true; }
                    catch (IllegalStateException e) { assertThat(e.getMessage()).contains("tối đa 3"); return false; }
                }));
            }
            start.countDown();
            int created = 0;
            for (var result : results) if (result.get(30, TimeUnit.SECONDS)) created++;
            assertThat(created).isEqualTo(1);
        }
        assertThat(users.countByRole(UserRole.ADMIN)).isEqualTo(3);
        assertThatThrownBy(() -> service.create(new CreateUserRequest("fourth-admin", UserRole.ADMIN)))
            .isInstanceOf(IllegalStateException.class).hasMessageContaining("tối đa 3");
        assertThat(users.existsByUsername("fourth-admin")).isFalse();
        service.create(new CreateUserRequest("staff-unaffected", UserRole.STAFF));
        assertThat(users.existsByUsername("staff-unaffected")).isTrue();
    }
}
