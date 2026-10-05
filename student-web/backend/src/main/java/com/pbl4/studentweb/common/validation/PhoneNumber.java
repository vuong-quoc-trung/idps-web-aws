package com.pbl4.studentweb.common.validation;
import jakarta.validation.*;
import java.lang.annotation.*;
@Target({ElementType.FIELD, ElementType.PARAMETER, ElementType.RECORD_COMPONENT, ElementType.TYPE_USE})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = PhoneNumber.Validator.class)
public @interface PhoneNumber {
    String message() default "Số điện thoại không hợp lệ: dùng số Việt Nam hoặc +mã quốc gia";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
    class Validator implements ConstraintValidator<PhoneNumber, String> {
        public boolean isValid(String value, ConstraintValidatorContext context) { return ContactValues.validPhone(value); }
    }
}
