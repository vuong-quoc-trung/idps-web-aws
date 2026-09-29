package com.pbl4.studentweb.studentclass.dto;

import jakarta.validation.constraints.*;

/** Full replacement of editable catalog fields. */
public record StudentClassRequest(@NotBlank @Size(max = 30) String code,
        @Size(max = 100) String name,
        @NotNull @Positive Long majorId, @Positive Long programId, @Positive Integer cohort,
        @Size(max = 20) String academicYear, @NotNull Boolean active) {}
