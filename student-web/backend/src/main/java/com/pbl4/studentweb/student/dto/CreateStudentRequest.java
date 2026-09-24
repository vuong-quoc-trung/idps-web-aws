package com.pbl4.studentweb.student.dto;

import com.pbl4.studentweb.student.entity.Gender;
import jakarta.validation.constraints.*;
import java.time.LocalDate;

/** Admin-owned fields from the grey cells; username defaults to studentCode. */
public record CreateStudentRequest(
        @NotBlank @Size(max = 20) String studentCode,
        @NotBlank @Size(max = 120) String fullName,
        @Past LocalDate dateOfBirth, Gender gender,
        @Size(max = 20) String citizenId,
        @NotNull Long majorId, @NotNull Long classId,
        Long trainingProgramId, Long secondaryProgramId,
        @Email @Size(max = 150) String schoolEmail,
        @Size(max = 20) String familyPhoneNumber) {}
