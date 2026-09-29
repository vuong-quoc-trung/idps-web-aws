package com.pbl4.studentweb.student.dto;

import com.pbl4.studentweb.student.entity.*;
import java.time.LocalDate;
import java.time.LocalDateTime;

public record StudentDetail(
        Long id, Long userId, String studentCode, String fullName, String avatarUrl,
        LocalDate dateOfBirth, Gender gender, String placeOfBirth, String oldPlaceOfBirth,
        String ethnicity, String nationality, String religion, String citizenId, LocalDate citizenIdIssueDate,
        String healthInsuranceNumber, LocalDate healthInsuranceExpiry, boolean freeHealthInsurance,
        Long majorId, Long classId, Long trainingProgramId, Long secondaryProgramId,
        String schoolEmail, String personalEmail, String phoneNumber, String familyPhoneNumber,
        String facebookUrl, String bankAccountNumber, String bankName,
        ProfileStatus profileStatus, LocalDateTime profileCompletedAt, StudentStatus status) {}
