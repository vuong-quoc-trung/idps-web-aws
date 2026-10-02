package com.pbl4.studentweb.major.dto;

import jakarta.validation.constraints.*;

/** Full replacement of editable catalog fields. */
public record MajorRequest(@NotBlank @Size(max = 100) String shortCode,
        @NotBlank @Size(max = 150) String name,
        @Size(max = 5000) String description, @NotNull @Positive Long facultyId, @NotNull Boolean active) {}
