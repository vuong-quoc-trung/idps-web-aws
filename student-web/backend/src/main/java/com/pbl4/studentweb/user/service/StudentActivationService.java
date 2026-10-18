package com.pbl4.studentweb.user.service;

import com.pbl4.studentweb.student.repository.StudentRepository;
import com.pbl4.studentweb.user.repository.UserRepository;
import com.pbl4.studentweb.user.entity.UserRole;
import com.pbl4.studentweb.user.controller.StudentActivationController.Identity;
import com.pbl4.studentweb.common.validation.ContactValues;
import java.security.*;
import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class StudentActivationService {
    private final StudentRepository students;
    private final UserRepository users;
    private final PasswordSetupService setup;
    private final PasswordResetMailService mail;
    private final SecureRandom random;

    public StudentActivationService(StudentRepository students, UserRepository users,
            PasswordSetupService setup, PasswordResetMailService mail) {
        this.students = students;
        this.users = users;
        this.setup = setup;
        this.mail = mail;
        this.random = new SecureRandom();
    }

    private String normalize(String value) {
        return value == null ? "" : java.text.Normalizer.normalize(value.trim(), java.text.Normalizer.Form.NFC)
            .replaceAll("\\s+", " ").toLowerCase(Locale.ROOT);
    }
    private boolean same(String a, String b) { return normalize(a).equals(normalize(b)); }
    private String hash(String token) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(token.getBytes(StandardCharsets.UTF_8))); }
        catch (NoSuchAlgorithmException e) { throw new IllegalStateException(e); }
    }
    @Transactional
    public String verify(Identity r) {
        var found = students.findByStudentCode(r.studentCode().trim());
        if (found.isEmpty()) return null;
        var s = found.get();
        var u = users.findForUpdate(s.getUser().getId()).orElseThrow();
        if (!u.isEnabled() || !u.isPasswordSetupRequired() || u.getRole() != UserRole.STUDENT) return null;
        var now = LocalDateTime.now();
        if (u.getActivationCheckWindow() == null || !u.getActivationCheckWindow().plusHours(1).isAfter(now)) {
            u.setActivationCheckWindow(now); u.setActivationCheckCount(0);
        }
        if (u.getActivationCheckCount() >= 5) return null;
        u.setActivationCheckCount(u.getActivationCheckCount() + 1);
        if (s.getDateOfBirth() == null || s.getGender() == null || s.getCitizenId() == null || s.getCitizenId().isBlank()
            || !same(s.getFullName(), r.fullName()) || !s.getDateOfBirth().equals(r.dateOfBirth())
            || s.getGender() != r.gender() || !same(s.getCitizenId(), r.citizenId())
            || !same(s.getStudentClass().getClassCode(), r.classCode())
            || !Objects.equals(ContactValues.phone(s.getFamilyPhoneNumber()), ContactValues.phone(r.familyPhoneNumber()))) return null;
        byte[] bytes = new byte[32]; random.nextBytes(bytes);
        String proof = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
        u.setActivationProofHash(hash(proof)); u.setActivationProofExpiresAt(now.plusMinutes(5));
        return proof;
    }
    @Transactional
    public boolean send(String proof, String email) {
        var found = users.findForActivationProof(hash(proof));
        if (found.isEmpty()) return false;
        var u = found.get();
        if (!u.isEnabled() || !u.isPasswordSetupRequired() || u.getRole() != UserRole.STUDENT
                || u.getActivationProofExpiresAt() == null || !u.getActivationProofExpiresAt().isAfter(LocalDateTime.now())) return false;
        String token = setup.reissueActivation(u.getId());
        u.setPendingActivationEmail(email.trim());
        // SMTP failure rolls back proof consumption and token replacement; no secrets in response/logs.
        mail.sendActivation(email.trim(), token);
        return true;
    }
}
