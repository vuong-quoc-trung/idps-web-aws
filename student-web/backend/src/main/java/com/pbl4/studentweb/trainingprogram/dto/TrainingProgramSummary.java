package com.pbl4.studentweb.trainingprogram.dto;

import com.pbl4.studentweb.trainingprogram.entity.DegreeType;

public record TrainingProgramSummary(Long id, String code, String name, Long majorId, Integer cohort,
        DegreeType degreeType, Integer numberOfSemesters, Integer totalCredits,
        Integer requiredCredits, Integer electiveCredits, boolean active) {}
