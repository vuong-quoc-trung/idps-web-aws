package com.pbl4.studentweb.studentclass.dto;

import jakarta.validation.constraints.*;

/** programId is required; optional majorId must match the program's major. */
public record StudentClassRequest(@Size(max = 100) String name,
        @Positive Long majorId, @NotNull @Positive Long programId, @Min(1000) @Max(9999) Integer cohort,
        @Size(max = 20) String academicYear, @NotNull Boolean active) {}
