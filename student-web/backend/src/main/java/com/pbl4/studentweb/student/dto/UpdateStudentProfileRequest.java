package com.pbl4.studentweb.student.dto;

import jakarta.validation.constraints.*;
import java.time.LocalDate;
public record UpdateStudentProfileRequest(
        @Size(max = 500) String avatarUrl,
        @Size(max = 150) String placeOfBirth, @Size(max = 150) String oldPlaceOfBirth,
        @Size(max = 50) String ethnicity, @Size(max = 50) String nationality,
        @Size(max = 50) String religion, @PastOrPresent LocalDate citizenIdIssueDate,
        @Size(max = 30) String healthInsuranceNumber, LocalDate healthInsuranceExpiry,
        boolean freeHealthInsurance,
        @Email @Size(max = 150) String personalEmail, @Size(max = 20) String phoneNumber,
        @Size(max = 500) String facebookUrl) {}
