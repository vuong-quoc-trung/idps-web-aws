package com.pbl4.studentweb.user.service;

import com.pbl4.studentweb.user.entity.User;
import com.pbl4.studentweb.user.repository.UserRepository;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.LocalDateTime;
import java.util.Base64;
import java.util.HexFormat;
import lombok.RequiredArgsConstructor;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
public class PasswordSetupService {
    private final UserRepository users;
    private final PasswordEncoder encoder;
    private final SecureRandom random = new SecureRandom();

    // Internal admin onboarding only. Deliver the returned secret through a trusted channel.
    public String prepareNewAccount(User user) {
        if (user.getId() != null) throw new IllegalArgumentException("Account already exists");
        String token = randomToken();
        user.setPasswordHash(encoder.encode(randomToken()));
        user.setPasswordSetupRequired(true);
        user.setActivationTokenHash(hash(token));
        user.setActivationExpiresAt(LocalDateTime.now().plusHours(24));
        return token;
    }

    @Transactional
    public void setInitialPassword(String token, String password) {
        if (token == null || token.isBlank()) throw new IllegalArgumentException("Invalid activation token");
        if (password == null || password.length() < 12 || password.getBytes(StandardCharsets.UTF_8).length > 72)
            throw new IllegalArgumentException("Password must have at least 12 characters and at most 72 UTF-8 bytes");
        User user = users.findForActivation(hash(token))
                .orElseThrow(() -> new IllegalArgumentException("Invalid or expired activation token"));
        if (!user.isEnabled() || !user.isPasswordSetupRequired() || user.getActivationExpiresAt() == null
                || !user.getActivationExpiresAt().isAfter(LocalDateTime.now()))
            throw new IllegalArgumentException("Invalid or expired activation token");
        user.setPasswordHash(encoder.encode(password));
        user.setPasswordSetupRequired(false);
        user.setActivationTokenHash(null);
        user.setActivationExpiresAt(null);
    }

    private String randomToken() {
        byte[] bytes = new byte[32];
        random.nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    private String hash(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }
}
