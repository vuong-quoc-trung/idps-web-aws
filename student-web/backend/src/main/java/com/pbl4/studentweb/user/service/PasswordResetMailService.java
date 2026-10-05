package com.pbl4.studentweb.user.service;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class PasswordResetMailService {
    private final ObjectProvider<JavaMailSender> sender;
    private final boolean enabled;
    private final String from;
    public PasswordResetMailService(ObjectProvider<JavaMailSender> sender,
            @Value("${app.password-reset.mail-enabled:false}") boolean enabled,
            @Value("${app.password-reset.from:}") String from) {
        this.sender = sender; this.enabled = enabled; this.from = from;
    }
    public boolean available() { return enabled && !from.isBlank() && sender.getIfAvailable() != null; }
    public void send(String recipient, String code) {
        var message = new SimpleMailMessage();
        message.setFrom(from); message.setTo(recipient);
        message.setSubject("PBL4 - Mã xác thực đặt lại mật khẩu");
        message.setText("Mã xác thực của bạn: " + code
            + "\nMã có hiệu lực 10 phút và chỉ dùng một lần. Không chia sẻ mã này."
            + "\nNếu bạn không yêu cầu đặt lại mật khẩu, hãy bỏ qua email này.");
        sender.getObject().send(message);
    }
}
