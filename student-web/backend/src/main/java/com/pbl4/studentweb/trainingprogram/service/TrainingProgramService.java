package com.pbl4.studentweb.trainingprogram.service;

import com.pbl4.studentweb.trainingprogram.repository.TrainingProgramRepository;
import com.pbl4.studentweb.trainingprogram.mapper.TrainingProgramMapper;
import com.pbl4.studentweb.trainingprogram.dto.TrainingProgramSummary;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class TrainingProgramService {
    private final TrainingProgramRepository repository;
    private final TrainingProgramMapper mapper;

    // Internal service only; caller authorization belongs to the future API layer.
    public Page<TrainingProgramSummary> findAll(Pageable pageable) {
        return repository.findAll(pageable).map(mapper::toSummary);
    }
}
