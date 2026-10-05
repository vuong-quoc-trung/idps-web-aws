package com.pbl4.studentweb.user.controller;

import com.pbl4.studentweb.user.service.*;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/auth")
public class StudentPasswordController {
    private final StudentPasswordService passwords;
    private final PasswordResetMailService mail;
    private final CurrentAccount account;
    public record ForgotRequest(@NotBlank @Size(max=50) String studentCode) {}
    public record ResetRequest(@NotBlank @Size(max=50) String studentCode,
            @NotBlank @Pattern(regexp="[0-9]{6}") String code,
            @NotBlank @Size(min=12,max=72) String newPassword) {
        @Override public String toString() { return "ResetRequest[redacted]"; }
    }
    public record ChangeRequest(@NotBlank @Size(max=72) String currentPassword,
            @NotBlank @Size(min=12,max=72) String newPassword) {
        @Override public String toString() { return "ChangeRequest[redacted]"; }
    }
    public record Message(String message) {}
    @PostMapping("/forgot-password")
    public ResponseEntity<Message> forgot(@Valid @RequestBody ForgotRequest request) {
        if (!mail.available()) return ResponseEntity.status(503).body(new Message("Chức năng gửi email chưa được cấu hình"));
        passwords.requestReset(request.studentCode());
        return ResponseEntity.accepted().body(new Message("Nếu tài khoản đủ điều kiện, mã xác thực sẽ được gửi tới email trường. Vui lòng kiểm tra hộp thư."));
    }
    @PostMapping("/reset-password")
    public ResponseEntity<Void> reset(@Valid @RequestBody ResetRequest request) {
        if (!passwords.reset(request.studentCode(), request.code(), request.newPassword()))
            throw new IllegalArgumentException("Mã xác thực không hợp lệ hoặc đã hết hạn");
        return ResponseEntity.noContent().build();
    }
    @PostMapping("/change-password")
    public ResponseEntity<Void> change(Authentication authentication, @Valid @RequestBody ChangeRequest request) {
        if (!passwords.change(account.userId(authentication), request.currentPassword(), request.newPassword()))
            throw new IllegalArgumentException("Mật khẩu hiện tại không đúng");
        return ResponseEntity.noContent().build();
    }
}
