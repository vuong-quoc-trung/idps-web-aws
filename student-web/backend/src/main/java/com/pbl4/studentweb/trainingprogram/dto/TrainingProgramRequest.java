package com.pbl4.studentweb.trainingprogram.dto;

import jakarta.validation.constraints.*;

/** Full replacement of editable catalog fields. */
public record TrainingProgramRequest(@NotBlank @Size(max = 30) String code,
        @NotBlank @Size(max = 200) String name,
        @NotNull @Positive Long majorId, @Positive Integer cohort,
        @Size(max = 50) String degreeType, @NotNull Boolean active) {}
