package com.pbl4.studentweb.student.dto;

import jakarta.validation.constraints.*;
import com.pbl4.studentweb.common.validation.HttpUrl;
import com.pbl4.studentweb.common.validation.PhoneNumber;
import com.pbl4.studentweb.common.validation.ContactEmail;
import java.time.LocalDate;
public record UpdateStudentProfileRequest(
        @HttpUrl @Size(max = 4096, message = "Đường dẫn ảnh đại diện không được vượt quá 4096 ký tự") String avatarUrl,
        @Size(max = 150) String placeOfBirth, @Size(max = 150) String oldPlaceOfBirth,
        @Size(max = 50) String ethnicity, @Size(max = 150) String nationality,
        @Size(max = 50) String religion, @PastOrPresent LocalDate citizenIdIssueDate,
        @Size(max = 30) String healthInsuranceNumber, LocalDate healthInsuranceExpiry,
        boolean freeHealthInsurance,
        @ContactEmail String personalEmail, @PhoneNumber String phoneNumber,
        @HttpUrl @Size(max = 500) String facebookUrl,
        @Size(max = 2) String birthCountryCode, @Size(max = 2) String originCountryCode) {}
