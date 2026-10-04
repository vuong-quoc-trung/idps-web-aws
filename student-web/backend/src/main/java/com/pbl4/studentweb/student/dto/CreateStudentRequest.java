package com.pbl4.studentweb.student.dto;

import com.pbl4.studentweb.student.entity.Gender;
import jakarta.validation.constraints.*;
import java.time.LocalDate;

/** Class determines the primary program and major; optional IDs are consistency assertions. */
public record CreateStudentRequest(
        @NotBlank @Size(max = 120) String fullName,
        @Past LocalDate dateOfBirth, Gender gender,
        @Size(max = 20) String citizenId,
        @Positive Long majorId, @NotNull @Positive Long classId,
        @Positive Long trainingProgramId, @Positive Long secondaryProgramId,
        @Size(max = 20) String familyPhoneNumber) {}
