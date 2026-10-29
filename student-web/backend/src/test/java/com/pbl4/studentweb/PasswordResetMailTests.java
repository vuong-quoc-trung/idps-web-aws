package com.pbl4.studentweb;

import com.pbl4.studentweb.user.service.PasswordResetMailService;
import jakarta.mail.internet.MimeMessage;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.support.StaticListableBeanFactory;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.MailPreparationException;
import org.springframework.test.util.ReflectionTestUtils;
import static org.assertj.core.api.Assertions.*;

class PasswordResetMailTests {
    private static class CaptureSender extends JavaMailSenderImpl {
        MimeMessage captured;
        @Override public void send(MimeMessage message) { captured = message; }
    }

    private PasswordResetMailService activationService(CaptureSender sender, String baseUrl) {
        var beans = new StaticListableBeanFactory();
        beans.addBean("mail", sender);
        var service = new PasswordResetMailService(beans.getBeanProvider(JavaMailSender.class), true, "sender@example.com");
        ReflectionTestUtils.setField(service, "publicBaseUrl", baseUrl);
        return service;
    }

    @ParameterizedTest
    @ValueSource(strings = {"http://localhost:5173", "http://127.0.0.1:5173", "http://[::1]:5173", "https://students.example.com"})
    void sendsActivationForLocalhostOrHttps(String baseUrl) throws Exception {
        var sender = new CaptureSender();
        activationService(sender, baseUrl).sendActivation("student@example.com", "test-activation-token");
        sender.captured.saveChanges();
        assertThat(sender.captured.getSubject()).isEqualTo("DUT student system - Kích hoạt tài khoản sinh viên");
        assertActivationParts(sender.captured, baseUrl + "/activate#token=test-activation-token");
    }

    @Test void rejectsLabHttpBeforeSending() {
        var sender = new CaptureSender();
        var service = activationService(sender, "http://192.168.10.1");
        assertThatThrownBy(() -> service.sendActivation("student@example.com", "test-token"))
            .isInstanceOf(MailPreparationException.class).hasMessage("Invalid activation public URL");
        assertThat(sender.captured).isNull();
    }

    @ParameterizedTest
    @ValueSource(strings = {"https://students.example.com?x=1", "https://students.example.com#fragment",
        "https://user:password@students.example.com", "//students.example.com", "ftp://students.example.com",
        "https://students.example.com/invalid path"})
    void rejectsInvalidActivationUrls(String baseUrl) {
        var sender = new CaptureSender();
        var service = activationService(sender, baseUrl);
        assertThatThrownBy(() -> service.sendActivation("student@example.com", "test-token"))
            .isInstanceOf(MailPreparationException.class).hasMessage("Invalid activation public URL");
        assertThat(sender.captured).isNull();
    }

    private void assertActivationParts(jakarta.mail.Part part, String link) throws Exception {
        if (part.isMimeType("multipart/*")) {
            var multipart = (jakarta.mail.Multipart) part.getContent();
            for (int i = 0; i < multipart.getCount(); i++) assertActivationParts(multipart.getBodyPart(i), link);
        } else if (part.isMimeType("text/*")) {
            assertThat((String) part.getContent()).contains(link, "24 giờ");
        }
    }

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
