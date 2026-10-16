package com.pbl4.studentweb;

import com.pbl4.studentweb.user.service.PasswordResetMailService;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.support.StaticListableBeanFactory;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import static org.assertj.core.api.Assertions.*;

class PasswordResetMailTests {
    @Test void deliversUtf8HtmlAndPlainTextWithoutSendingRealEmail() throws Exception {
        class CaptureSender extends JavaMailSenderImpl {
            MimeMessage captured;
            @Override public void send(MimeMessage message) { captured = message; }
        }
        var sender = new CaptureSender();
        var beans = new StaticListableBeanFactory();
        beans.addBean("mail", sender);
        var service = new PasswordResetMailService(beans.getBeanProvider(JavaMailSender.class), true, "sender@example.com");
        service.send("student@example.com", "012345");
        sender.captured.saveChanges();
        assertThat(sender.captured.getSubject()).isEqualTo("DUT student system - Mã xác thực đặt lại mật khẩu");
        assertThat(sender.captured.getAllRecipients()[0].toString()).isEqualTo("student@example.com");
        assertThat(sender.captured.isMimeType("multipart/*")).isTrue();
        assertParts(sender.captured);
    }
    private void assertParts(jakarta.mail.Part part) throws Exception {
        if (part.isMimeType("multipart/*")) {
            var multipart = (jakarta.mail.Multipart) part.getContent();
            for (int i = 0; i < multipart.getCount(); i++) assertParts(multipart.getBodyPart(i));
        } else if (part.isMimeType("text/*")) {
            assertThat((String) part.getContent()).contains("012345", "DUT student system", "5 phút");
        }
    }
}
