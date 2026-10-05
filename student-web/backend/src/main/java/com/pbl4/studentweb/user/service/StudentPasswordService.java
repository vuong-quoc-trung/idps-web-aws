package com.pbl4.studentweb.user.service;

import com.pbl4.studentweb.user.entity.User;
import com.pbl4.studentweb.user.entity.UserRole;
import com.pbl4.studentweb.user.repository.UserRepository;
import com.pbl4.studentweb.student.repository.StudentRepository;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.time.LocalDateTime;
import java.util.Locale;
import lombok.RequiredArgsConstructor;
import org.springframework.mail.MailException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
public class StudentPasswordService {
    private final UserRepository users;
    private final StudentRepository students;
    private final PasswordEncoder encoder;
    private final PasswordResetMailService mail;
    private final SecureRandom random = new SecureRandom();

    private boolean eligible(User u) {
        return u.isEnabled() && !u.isPasswordSetupRequired() && u.getRole() == UserRole.STUDENT;
    }
    public static void validatePassword(String password) {
        if (password == null || password.isBlank() || password.length() < 12
                || password.getBytes(StandardCharsets.UTF_8).length > 72)
            throw new IllegalArgumentException("Mật khẩu cần ít nhất 12 ký tự và tối đa 72 byte UTF-8");
    }
    @Transactional
    public void requestReset(String studentCode) {
        var found = students.findByStudentCode(studentCode.trim()).map(s -> s.getUser());
        if (found.isEmpty()) return;
        var u = users.findForUpdate(found.get().getId()).orElseThrow();
        if (!eligible(u)) return;
        var student = students.findByUserId(u.getId());
        if (student.isEmpty() || student.get().getSchoolEmail() == null) return;
        var now = LocalDateTime.now();
        if (u.getResetSentAt() != null && u.getResetSentAt().plusSeconds(60).isAfter(now)) return;
        if (u.getResetWindowStartedAt() == null || !u.getResetWindowStartedAt().plusHours(1).isAfter(now)) {
            u.setResetWindowStartedAt(now); u.setResetSendCount(0);
        }
        if (u.getResetSendCount() >= 5) return;
        String code = String.format(Locale.ROOT, "%06d", random.nextInt(1000000));
        u.setResetSentAt(now); u.setResetSendCount(u.getResetSendCount() + 1);
        u.setResetAttempts(0); u.setResetCodeHash(encoder.encode(code));
        u.setResetExpiresAt(now.plusMinutes(10));
        try { mail.send(student.get().getSchoolEmail(), code); }
        catch (MailException e) {
            // Do not leak account existence or SMTP details, and retain the send limit.
            clearReset(u);
            org.slf4j.LoggerFactory.getLogger(getClass()).warn("Password reset delivery failed; check SMTP configuration");
        }
    }
    // Return failure instead of throwing so failed-attempt counters commit.
    @Transactional
    public boolean reset(String studentCode, String code, String password) {
        validatePassword(password);
        var found = students.findByStudentCode(studentCode.trim()).map(s -> s.getUser());
        if (found.isEmpty()) return false;
        var u = users.findForUpdate(found.get().getId()).orElseThrow();
        if (!eligible(u) || u.getResetCodeHash() == null || u.getResetExpiresAt() == null
                || !u.getResetExpiresAt().isAfter(LocalDateTime.now()) || u.getResetAttempts() >= 5) return false;
        u.setResetAttempts(u.getResetAttempts() + 1);
        if (!encoder.matches(code, u.getResetCodeHash())) {
            if (u.getResetAttempts() >= 5) clearReset(u);
            return false;
        }
        updatePassword(u, password);
        return true;
    }
    @Transactional
    public boolean change(Long userId, String currentPassword, String newPassword) {
        validatePassword(newPassword);
        var u = users.findForUpdate(userId).orElseThrow();
        if (!eligible(u) || !encoder.matches(currentPassword, u.getPasswordHash())) return false;
        if (encoder.matches(newPassword, u.getPasswordHash()))
            throw new IllegalArgumentException("Mật khẩu mới phải khác mật khẩu hiện tại");
        updatePassword(u, newPassword);
        return true;
    }
    private void updatePassword(User u, String password) {
        u.setPasswordHash(encoder.encode(password));
        u.setCredentialVersion(u.getCredentialVersion() + 1);
        clearReset(u);
        u.setActivationTokenHash(null); u.setActivationExpiresAt(null);
    }
    private void clearReset(User u) { u.setResetCodeHash(null); u.setResetExpiresAt(null); }
}
