package com.pbl4.studentweb.trainingprogram.mapper;

import com.pbl4.studentweb.trainingprogram.entity.TrainingProgram;
import com.pbl4.studentweb.trainingprogram.dto.TrainingProgramSummary;
import org.springframework.stereotype.Component;

@Component
public class TrainingProgramMapper {
    public TrainingProgramSummary toSummary(TrainingProgram e) {
        return new TrainingProgramSummary(e.getId(), e.getProgramCode(), e.getProgramName(), e.getMajor().getId(), e.isActive());
    }
}
