package com.pbl4.studentweb.faculty.dto;

import jakarta.validation.constraints.*;

public record FacultyRequest(@NotBlank @Size(max = 100) String shortCode,
        @NotBlank @Size(max = 150) String name,
        @Size(max = 5000) String description, @NotNull Boolean active) {}
