package com.pbl4.studentweb.trainingprogram.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import com.pbl4.studentweb.trainingprogram.entity.TrainingProgram;

public interface TrainingProgramRepository extends JpaRepository<TrainingProgram, Long> {
}
