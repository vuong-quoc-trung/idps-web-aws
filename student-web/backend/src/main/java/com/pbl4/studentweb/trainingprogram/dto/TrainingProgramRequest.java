package com.pbl4.studentweb.trainingprogram.dto;

import jakarta.validation.constraints.*;
import com.pbl4.studentweb.trainingprogram.entity.DegreeType;

/** Full replacement of editable catalog fields. */
public record TrainingProgramRequest(@NotBlank @Size(max = 30) String code,
        @NotBlank @Size(max = 200) String name,
        @NotNull @Positive Long majorId, @Positive Integer cohort,
        DegreeType degreeType, @Positive Integer numberOfSemesters,
        @PositiveOrZero Integer totalCredits, @PositiveOrZero Integer requiredCredits,
        @PositiveOrZero Integer electiveCredits, @NotNull Boolean active) {}
