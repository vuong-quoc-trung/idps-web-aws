package com.pbl4.studentweb.student.dto;

import com.pbl4.studentweb.student.entity.*;
import jakarta.validation.constraints.*;
import com.pbl4.studentweb.common.validation.PhoneNumber;
import java.time.LocalDate;

/** Class determines the primary program and major. Student code, school email and username remain immutable. */
public record UpdateStudentRequest(
        @NotBlank @Size(max = 120) String fullName, @Past LocalDate dateOfBirth, Gender gender,
        @Size(max = 20) String citizenId, @Positive Long majorId, @NotNull @Positive Long classId,
        @Positive Long trainingProgramId, @Positive Long secondaryProgramId,
        @PhoneNumber String familyPhoneNumber,
        @Size(max = 50) String bankAccountNumber, @Size(max = 100) String bankName,
        @NotNull StudentStatus status) {}
