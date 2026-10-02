package com.pbl4.studentweb.trainingprogram.dto;

import jakarta.validation.constraints.*;
import com.pbl4.studentweb.trainingprogram.entity.DegreeType;

/** Full replacement of editable catalog fields. */
public record TrainingProgramRequest(@NotBlank @Size(max = 200) String name,
        @NotNull @Positive Long majorId, @NotNull @Min(1000) @Max(9999) Integer cohort,
        @NotNull DegreeType degreeType, @Positive Integer numberOfSemesters,
        @PositiveOrZero Integer totalCredits, @PositiveOrZero Integer requiredCredits,
        @PositiveOrZero Integer electiveCredits, @NotNull Boolean active) {}
