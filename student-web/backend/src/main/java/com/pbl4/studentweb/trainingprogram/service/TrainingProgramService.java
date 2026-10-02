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
    private final com.pbl4.studentweb.common.code.CodeGenerationService codes;
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
        var entity = new TrainingProgram();
        apply(entity, request);
        return mapper.toSummary(repository.saveAndFlush(entity));
    }

    @Transactional
    public TrainingProgramSummary update(Long id, @NotNull @Valid TrainingProgramRequest request) {
        var entity = require(id);
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
        if ((e.getId() == null || !e.getMajor().getId().equals(major.getId()) || r.active())
                && (!major.isActive() || !major.getFaculty().isActive()))
            throw new IllegalArgumentException("Major and faculty must be active");
        validateCredits(r);
        if (e.getId() != null && e.getCohort() != null && !java.util.Objects.equals(e.getCohort(), r.cohort())
                && (classes.existsByProgramId(e.getId()) || students.existsByTrainingProgramIdOrSecondaryProgramId(e.getId(), e.getId())))
            throw new IllegalStateException("Cannot change cohort of a program in use");
        String code = codes.program(major, r.cohort(), r.degreeType());
        if (e.getId() == null ? repository.existsByProgramCode(code) : repository.existsByProgramCodeAndIdNot(code, e.getId()))
            throw new IllegalStateException("Program code already exists");
        e.setProgramCode(code);
        e.setMajor(major);
        e.setCohort(r.cohort());
        e.setDegreeType(r.degreeType());
        e.setNumberOfSemesters(r.numberOfSemesters());
        e.setTotalCredits(r.totalCredits());
        e.setRequiredCredits(r.requiredCredits());
        e.setElectiveCredits(r.electiveCredits());

        e.setProgramName(optional(r.name()));
        e.setActive(r.active());
    }

    private void validateCredits(TrainingProgramRequest r) {
        if (r.totalCredits() == null) return;
        if ((r.requiredCredits() != null && r.requiredCredits() > r.totalCredits())
                || (r.electiveCredits() != null && r.electiveCredits() > r.totalCredits()))
            throw new IllegalArgumentException("Component credits cannot exceed total credits");
        if (r.requiredCredits() != null && r.electiveCredits() != null
                && (long) r.requiredCredits() + r.electiveCredits() != r.totalCredits())
            throw new IllegalArgumentException("Total credits must equal required plus elective credits");
    }
}
