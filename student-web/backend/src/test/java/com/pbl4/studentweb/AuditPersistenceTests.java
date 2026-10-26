package com.pbl4.studentweb;

import com.pbl4.studentweb.accesslog.repository.AccessLogRepository;
import com.pbl4.studentweb.user.entity.*;
import com.pbl4.studentweb.user.repository.UserRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.context.WebApplicationContext;
import static org.assertj.core.api.Assertions.*;
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

// No test transaction: verify that actual request transactions commit audit rows.
@SpringBootTest(properties = {
    "spring.datasource.url=jdbc:h2:mem:auditpersistence;MODE=PostgreSQL;DB_CLOSE_DELAY=-1",
    "spring.datasource.username=sa", "spring.datasource.password=",
    "spring.jpa.hibernate.ddl-auto=create-drop", "spring.jpa.properties.hibernate.default_schema=PUBLIC",
    "app.bootstrap.enabled=false", "logging.level.root=WARN"
})
class AuditPersistenceTests {
    @Autowired WebApplicationContext context;
    @Autowired UserRepository users;
    @Autowired AccessLogRepository logs;
    @Autowired PasswordEncoder encoder;
    @Test void successfulMutationAndFailedLoginAreCommitted() throws Exception {
        var mvc = MockMvcBuilders.webAppContextSetup(context).apply(springSecurity()).build();
        var user = new User();
        user.setUsername("audit-student"); user.setRole(UserRole.STUDENT);
        user.setPasswordSetupRequired(false); user.setPasswordHash(encoder.encode("Original-password-123"));
        users.saveAndFlush(user);
        var session = (MockHttpSession) mvc.perform(post("/api/auth/login").with(csrf())
            .param("username", "audit-student").param("password", "Original-password-123")
            .header("X-Request-Id", "edge-login-123").header("X-Forwarded-For", "192.0.2.44").header("User-Agent", "Mozilla/5.0 AuditTest"))
            .andExpect(status().isNoContent()).andReturn().getRequest().getSession(false);
        mvc.perform(post("/api/auth/change-password").session(session).with(csrf())
            .contentType("application/json")
            .content("{\"currentPassword\":\"Original-password-123\",\"newPassword\":\"Changed-password-123\"}"))
            .andExpect(status().isNoContent());
        mvc.perform(post("/api/auth/login").with(csrf()).param("username", "audit-student").param("password", "wrong"))
            .andExpect(status().isUnauthorized());
        mvc.perform(get("/api/auth/csrf").header("User-Agent", "Mozilla/5.0 Reads"))
            .andExpect(status().isOk());
        var entries = logs.findAll();
        assertThat(entries).anySatisfy(e -> {
            assertThat(e.getRequestId()).isEqualTo("edge-login-123");
            assertThat(e.getClientIp()).isEqualTo("192.0.2.44");
            assertThat(e.getUserAgent()).isEqualTo("Mozilla");
        });
        assertThat(entries).anySatisfy(e -> {
            assertThat(e.getRequestPath()).isEqualTo("/api/auth/csrf");
            assertThat(e.getUserAgent()).isEqualTo("Mozilla");
            assertThat(e.getStatusCode()).isEqualTo(200);
        });
        assertThat(entries).anySatisfy(e -> {
            assertThat(e.getRequestPath()).isEqualTo("/api/auth/change-password");
            assertThat(e.getStatusCode()).isEqualTo(204);
            assertThat(e.getAction()).isEqualTo("REQUEST_SUCCEEDED");
            assertThat(e.getUser().getId()).isEqualTo(user.getId());
        });
        assertThat(entries).anySatisfy(e -> {
            assertThat(e.getRequestPath()).isEqualTo("/api/auth/login");
            assertThat(e.getStatusCode()).isEqualTo(401);
        });
    }
}
