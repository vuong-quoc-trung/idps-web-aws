package com.pbl4.studentweb.common.validation;

import jakarta.validation.*;
import java.lang.annotation.*;
import java.net.URI;

@Target({ElementType.FIELD, ElementType.PARAMETER, ElementType.RECORD_COMPONENT})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = HttpUrl.Validator.class)
public @interface HttpUrl {
    String message() default "URL phải là đường dẫn HTTP/HTTPS hợp lệ";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};

    class Validator implements ConstraintValidator<HttpUrl, String> {
        public boolean isValid(String value, ConstraintValidatorContext context) {
            if (value == null) return true;
            if (value.chars().anyMatch(c -> c < 32 || c == 127)) return false;
            String url = value.trim();
            if (url.isEmpty()) return true;
            try {
                URI uri = new URI(url);
                return ("http".equalsIgnoreCase(uri.getScheme()) || "https".equalsIgnoreCase(uri.getScheme()))
                        && uri.getHost() != null && uri.getRawUserInfo() == null
                        && (uri.getPort() == -1 || uri.getPort() >= 1 && uri.getPort() <= 65535);
            } catch (java.net.URISyntaxException e) {
                return false;
            }
        }
    }
}
