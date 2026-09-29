package com.pbl4.studentweb.student.dto;

import com.pbl4.studentweb.student.entity.*;
import jakarta.validation.constraints.*;
import java.time.LocalDate;

/** Admin-owned fields. Student code and username remain immutable. */
public record UpdateStudentRequest(
        @NotBlank @Size(max = 120) String fullName, @Past LocalDate dateOfBirth, Gender gender,
        @Size(max = 20) String citizenId, @NotNull @Positive Long majorId, @NotNull @Positive Long classId,
        @Positive Long trainingProgramId, @Positive Long secondaryProgramId,
        @Email @Size(max = 150) String schoolEmail, @Size(max = 20) String familyPhoneNumber,
        @Size(max = 50) String bankAccountNumber, @Size(max = 100) String bankName,
        @NotNull StudentStatus status) {}
