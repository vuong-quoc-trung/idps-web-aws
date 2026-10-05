package com.pbl4.studentweb.common.validation;
import jakarta.validation.*;
import java.lang.annotation.*;
@Target({ElementType.FIELD, ElementType.PARAMETER, ElementType.RECORD_COMPONENT, ElementType.TYPE_USE})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = ContactEmail.Validator.class)
public @interface ContactEmail {
    String message() default "Email không đúng định dạng";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
    class Validator implements ConstraintValidator<ContactEmail, String> {
        public boolean isValid(String value, ConstraintValidatorContext context) { return ContactValues.validEmail(value); }
    }
}
