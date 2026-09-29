package com.pbl4.studentweb.configuration;

import com.pbl4.studentweb.user.entity.*;
import com.pbl4.studentweb.user.repository.UserRepository;
import java.nio.charset.StandardCharsets;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
@RequiredArgsConstructor
@ConditionalOnProperty(name = "app.bootstrap.enabled", havingValue = "true")
public class AdminBootstrap implements CommandLineRunner {
    private final UserRepository users;
    private final PasswordEncoder encoder;
    @Value("${app.bootstrap.admin-username:}") private String username;
    @Value("${app.bootstrap.admin-password:}") private String password;

    @Override
    @Transactional
    public void run(String... args) {
        if (users.existsByRole(UserRole.ADMIN)) return;
        if (username.isBlank() || username.length() > 50 || password.length() < 12
                || password.getBytes(StandardCharsets.UTF_8).length > 72)
            throw new IllegalStateException("Bootstrap requires an admin username and a password of at least 12 characters, at most 72 UTF-8 bytes");
        if (users.existsByUsername(username.trim())) throw new IllegalStateException("Bootstrap username is already used");
        var admin = new User();
        admin.setUsername(username.trim());
        admin.setRole(UserRole.ADMIN);
        admin.setPasswordHash(encoder.encode(password));
        admin.setPasswordSetupRequired(false);
        users.save(admin);
    }
}
