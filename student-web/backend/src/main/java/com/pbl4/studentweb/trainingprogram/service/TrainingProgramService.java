package com.pbl4.studentweb.trainingprogram.service;

import com.pbl4.studentweb.trainingprogram.repository.TrainingProgramRepository;
import com.pbl4.studentweb.trainingprogram.mapper.TrainingProgramMapper;
import com.pbl4.studentweb.trainingprogram.entity.TrainingProgram;
import com.pbl4.studentweb.trainingprogram.dto.*;
import com.pbl4.studentweb.common.exception.ResourceNotFoundException;
import com.pbl4.studentweb.student.repository.StudentRepository;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;
import static com.pbl4.studentweb.common.validation.TextValues.optional;

@Service
@Validated
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class TrainingProgramService {
    private final TrainingProgramRepository repository;
    private final TrainingProgramMapper mapper;
    private final StudentRepository students;
    private final com.pbl4.studentweb.major.repository.MajorRepository majors;
    private final com.pbl4.studentweb.studentclass.repository.StudentClassRepository classes;

    public Page<TrainingProgramSummary> findAll(Pageable pageable) {
        return repository.findAll(pageable).map(mapper::toSummary);
    }
    public TrainingProgramSummary findById(Long id) { return mapper.toSummary(require(id)); }

    @Transactional
    public TrainingProgramSummary create(@NotNull @Valid TrainingProgramRequest request) {
        if (repository.existsByProgramCode(request.code().trim())) throw new IllegalStateException("Code already exists");
        var entity = new TrainingProgram();
        apply(entity, request);
        return mapper.toSummary(repository.saveAndFlush(entity));
    }

    @Transactional
    public TrainingProgramSummary update(Long id, @NotNull @Valid TrainingProgramRequest request) {
        var entity = require(id);
        if (repository.existsByProgramCodeAndIdNot(request.code().trim(), id)) throw new IllegalStateException("Code already exists");
        apply(entity, request);
        return mapper.toSummary(repository.saveAndFlush(entity));
    }

    @Transactional
    public void delete(Long id) {
        var entity = require(id);
        if (classes.existsByProgramId(id) || students.existsByTrainingProgramIdOrSecondaryProgramId(id, id)) throw new IllegalStateException("Catalog is in use; deactivate it instead");
        repository.delete(entity);
        repository.flush();
    }

    private TrainingProgram require(Long id) {
        return repository.findById(id).orElseThrow(() -> new ResourceNotFoundException("TrainingProgram"));
    }
    private void apply(TrainingProgram e, TrainingProgramRequest r) {
        var major = majors.findById(r.majorId()).orElseThrow(() -> new ResourceNotFoundException("Major"));
        if (e.getId() != null && !e.getMajor().getId().equals(major.getId())
                && (classes.existsByProgramId(e.getId())
                    || students.existsByTrainingProgramIdOrSecondaryProgramId(e.getId(), e.getId())))
            throw new IllegalStateException("Cannot change the major of a program in use");
        if (r.active() && !major.isActive()) throw new IllegalArgumentException("Major is inactive");
        e.setMajor(major);
        e.setCohort(r.cohort());
        e.setDegreeType(optional(r.degreeType()));
        e.setProgramCode(r.code().trim());
        e.setProgramName(optional(r.name()));
        e.setActive(r.active());
    }
}
