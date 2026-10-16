package com.pbl4.studentweb.user.controller;

import com.pbl4.studentweb.user.service.*;
import com.pbl4.studentweb.student.entity.Gender;
import com.pbl4.studentweb.common.validation.*;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.time.LocalDate;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/auth/activation")
public class StudentActivationController {
    private final StudentActivationService service;
    private final PasswordResetMailService mail;
    public record Identity(@NotBlank @Size(max=20) String studentCode,
        @NotBlank @Size(max=120) String fullName, @NotNull @Past LocalDate dateOfBirth,
        @NotNull Gender gender, @NotBlank @Size(max=20) String citizenId,
        @NotBlank @Size(max=50) String classCode,
        @PhoneNumber String familyPhoneNumber) {
        @Override public String toString() { return "Identity[redacted]"; }
    }
    public record Verified(String proof) { @Override public String toString() { return "Verified[redacted]"; } }
    public record EmailRequest(@NotBlank @Size(max=100) String proof, @NotBlank @ContactEmail String email) {
        @Override public String toString() { return "EmailRequest[redacted]"; }
    }
    public record Message(String message) {}
    @PostMapping("/verify")
    public Verified verify(@Valid @RequestBody Identity request) {
        var proof = service.verify(request);
        if (proof == null) throw new IllegalArgumentException("Không thể xác minh thông tin hoặc đã vượt giới hạn. Vui lòng kiểm tra thông tin nhà trường cung cấp hoặc liên hệ quản trị viên.");
        return new Verified(proof);
    }
    @PostMapping("/send")
    public ResponseEntity<Message> send(@Valid @RequestBody EmailRequest request) {
        if (!mail.available()) return ResponseEntity.status(503).body(new Message("Chức năng gửi email chưa sẵn sàng"));
        try {
            if (!service.send(request.proof(), request.email())) throw new IllegalArgumentException("Phiên xác minh đã hết hạn hoặc đã dùng. Vui lòng đối chiếu lại thông tin.");
        } catch (org.springframework.mail.MailException e) {
            return ResponseEntity.status(503).body(new Message("Chưa gửi được email. Vui lòng thử lại sau."));
        }
        return ResponseEntity.accepted().body(new Message("Link kích hoạt đã được gửi. Vui lòng kiểm tra hộp thư và thư rác."));
    }
}
