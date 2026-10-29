package com.pbl4.studentweb.user.service;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Value;
import jakarta.mail.MessagingException;
import org.springframework.mail.MailPreparationException;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.web.util.HtmlUtils;
import java.nio.charset.StandardCharsets;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class PasswordResetMailService {
    private final ObjectProvider<JavaMailSender> sender;
    private final boolean enabled;
    private final String from;
    @Value("${app.activation.public-base-url:http://localhost:5173}")
    private String publicBaseUrl;
    public PasswordResetMailService(ObjectProvider<JavaMailSender> sender,
            @Value("${app.password-reset.mail-enabled:false}") boolean enabled,
            @Value("${app.password-reset.from:}") String from) {
        this.sender = sender; this.enabled = enabled; this.from = from;
    }
    public boolean available() { return enabled && !from.isBlank() && sender.getIfAvailable() != null; }
    public void send(String recipient, String code) {
        var mailSender = sender.getObject();
        var message = mailSender.createMimeMessage();
        try {
            var helper = new MimeMessageHelper(message, true, StandardCharsets.UTF_8.name());
            helper.setFrom(from);
            helper.setTo(recipient);
            helper.setSubject("DUT student system - Mã xác thực đặt lại mật khẩu");
            String text = "DUT student system\nHệ thống thông tin sinh viên\n\n"
                + "Mã xác thực đặt lại mật khẩu: " + code
                + "\nMã có hiệu lực 5 phút và chỉ dùng một lần. Không chia sẻ mã này."
                + "\nNếu bạn không yêu cầu đặt lại mật khẩu, hãy bỏ qua email này."
                + "\nĐây là email tự động, vui lòng không trả lời.";
            helper.setText(text, html(code));
        } catch (MessagingException e) {
            throw new MailPreparationException("Could not prepare password reset email", e);
        }
        mailSender.send(message);
    }

    public void sendActivation(String recipient, String token) {
        java.net.URI base;
        try {
            base = java.net.URI.create(publicBaseUrl);
        } catch (IllegalArgumentException e) {
            throw new MailPreparationException("Invalid activation public URL");
        }
        if (base.getHost() == null || base.getRawQuery() != null || base.getRawFragment() != null
                || base.getUserInfo() != null || !("https".equals(base.getScheme())
                || ("http".equals(base.getScheme()) && SetLocal.host(base.getHost()))))
            throw new MailPreparationException("Invalid activation public URL");
        String link = publicBaseUrl.replaceAll("/+$", "") + "/activate#token=" + token;
        var mailSender = sender.getObject();
        var message = mailSender.createMimeMessage();
        try {
            var helper = new MimeMessageHelper(message, true, StandardCharsets.UTF_8.name());
            helper.setFrom(from); helper.setTo(recipient);
            helper.setSubject("DUT student system - Kích hoạt tài khoản sinh viên");
            helper.setText("DUT student system\nMở link để đặt mật khẩu lần đầu: " + link
                + "\nLink chỉ dùng một lần, hiệu lực 24 giờ. Nếu không yêu cầu, hãy bỏ qua email.",
                "<html lang='vi'><body style='background:#eef3f9;padding:24px;font-family:Arial;color:#18324d'>"
                + "<div style='max-width:560px;margin:auto;background:white;padding:32px;border-top:5px solid #37b5df;border-radius:12px'>"
                + "<h2 style='color:#103d70'>DUT student system</h2><p>HỆ THỐNG THÔNG TIN SINH VIÊN</p>"
                + "<h1>Kích hoạt tài khoản</h1><p>Thông tin của bạn đã được đối chiếu. Mở liên kết bên dưới để đặt mật khẩu lần đầu.</p>"
                + "<p style='padding:20px 0'><a style='background:#103d70;color:white;padding:14px 24px;border-radius:8px;text-decoration:none' href='"
                + HtmlUtils.htmlEscape(link) + "'>Kích hoạt tài khoản</a></p>"
                + "<p>Link có hiệu lực <strong>24 giờ</strong> và chỉ dùng một lần. Không chia sẻ liên kết này.</p>"
                + "<p>Nếu bạn không yêu cầu, hãy bỏ qua email. Đây là email tự động, vui lòng không trả lời.</p></div></body></html>");
        } catch (MessagingException e) { throw new MailPreparationException("Could not prepare activation email", e); }
        mailSender.send(message);
    }
    private static class SetLocal {
        static boolean host(String value) { return java.util.Set.of("localhost", "127.0.0.1", "[::1]").contains(value); }
    }

    private String html(String code) {
        return """
            <!doctype html>
            <html lang="vi"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
            <body style="margin:0;padding:0;background-color:#eef3f9;font-family:Arial,Helvetica,sans-serif;color:#18324d;">
              <div style="display:none;max-height:0;overflow:hidden;opacity:0;">Mã xác thực đặt lại mật khẩu của bạn có hiệu lực trong 5 phút.</div>
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#eef3f9;">
                <tr><td align="center" style="padding:32px 12px;">
                  <table role="presentation" width="560" cellspacing="0" cellpadding="0" style="width:100%;max-width:560px;background-color:#ffffff;border:1px solid #dce5ef;border-radius:16px;overflow:hidden;">
                    <tr><td style="padding:28px 28px 26px;background-color:#103d70;border-top:5px solid #37b5df;">
                      <p style="margin:0 0 8px;font-size:11px;font-weight:bold;letter-spacing:2px;color:#9cddf3;">CỔNG THÔNG TIN SINH VIÊN</p>
                      <p style="margin:0;font-size:25px;font-weight:bold;line-height:1.3;color:#ffffff;">DUT student system</p>
                      <p style="margin:10px 0 0;font-size:13px;line-height:1.6;color:#d1e2f4;">Bảo vệ tài khoản · Kết nối hành trình học tập</p>
                    </td></tr>
                    <tr><td style="padding:30px 28px;">
                      <p style="margin:0 0 12px;font-size:11px;font-weight:bold;letter-spacing:1.5px;color:#167a9e;">XÁC THỰC TÀI KHOẢN</p>
                      <h1 style="margin:0 0 18px;font-size:23px;line-height:1.4;color:#12365b;">Đặt lại mật khẩu</h1>
                      <p style="margin:0 0 10px;font-size:15px;line-height:1.7;">Chào bạn,</p>
                      <p style="margin:0 0 24px;font-size:15px;line-height:1.7;color:#50647a;">Chúng tôi nhận được yêu cầu đặt lại mật khẩu tài khoản sinh viên của bạn. Nhập mã dưới đây vào màn hình xác thực để tiếp tục.</p>
                      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#f0f7ff;border:1px solid #c9dff5;border-radius:12px;">
                        <tr><td align="center" style="padding:23px 12px;">
                          <p style="margin:0 0 12px;font-size:11px;letter-spacing:1.5px;font-weight:bold;color:#53708e;">MÃ XÁC THỰC CỦA BẠN</p>
                          <p style="margin:0;font-family:Consolas,monospace;font-size:34px;font-weight:bold;letter-spacing:6px;line-height:1.4;color:#103d70;">{{CODE}}</p>
                          <p style="margin:14px 0 0;font-size:13px;color:#50647a;">Hiệu lực <strong>5 phút</strong> &nbsp;·&nbsp; Chỉ sử dụng một lần</p>
                        </td></tr>
                      </table>
                      <p style="margin:24px 0 0;padding:14px 16px;background-color:#fff8e8;border-left:3px solid #e7b64b;font-size:13px;line-height:1.7;color:#71551e;"><strong>Giữ mã này riêng tư.</strong><br>Không chia sẻ mã xác thực hoặc mật khẩu với bất kỳ ai.</p>
                      <p style="margin:22px 0 0;font-size:13px;line-height:1.7;color:#64748b;">Nếu bạn không thực hiện yêu cầu này, hãy bỏ qua email. Mật khẩu của bạn chưa bị thay đổi.</p>
                    </td></tr>
                    <tr><td style="padding:20px 28px;background-color:#f7f9fc;border-top:1px solid #e5ecf3;">
                      <p style="margin:0 0 6px;font-size:13px;font-weight:bold;color:#365474;">DUT student system</p>
                      <p style="margin:0;font-size:12px;line-height:1.7;color:#718096;">Hệ thống thông tin sinh viên<br>Email được gửi tự động. Vui lòng không trả lời.</p>
                    </td></tr>
                  </table>
                </td></tr>
              </table>
            </body></html>
            """.replace("{{CODE}}", HtmlUtils.htmlEscape(code));
    }
}
