package com.pbl4.studentweb.studentclass.service;

import com.pbl4.studentweb.studentclass.repository.StudentClassRepository;
import com.pbl4.studentweb.studentclass.mapper.StudentClassMapper;
import com.pbl4.studentweb.studentclass.entity.StudentClass;
import com.pbl4.studentweb.studentclass.dto.*;
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
public class StudentClassService {
    private final com.pbl4.studentweb.common.code.CodeGenerationService codes;
    private final StudentClassRepository repository;
    private final StudentClassMapper mapper;
    private final StudentRepository students;
    private final com.pbl4.studentweb.trainingprogram.repository.TrainingProgramRepository programs;

    public Page<StudentClassSummary> findAll(Pageable pageable) {
        return repository.findAll(pageable).map(mapper::toSummary);
    }
    public StudentClassSummary findById(Long id) { return mapper.toSummary(require(id)); }

    @Transactional
    public StudentClassSummary create(@NotNull @Valid StudentClassRequest request) {
        var entity = new StudentClass();
        apply(entity, request);
        return mapper.toSummary(repository.saveAndFlush(entity));
    }

    @Transactional
    public StudentClassSummary update(Long id, @NotNull @Valid StudentClassRequest request) {
        var entity = require(id);
        apply(entity, request);
        return mapper.toSummary(repository.saveAndFlush(entity));
    }

    @Transactional
    public void delete(Long id) {
        var entity = require(id);
        if (students.existsByStudentClassId(id)) throw new IllegalStateException("Catalog is in use; deactivate it instead");
        repository.delete(entity);
        repository.flush();
    }

    private StudentClass require(Long id) {
        return repository.findById(id).orElseThrow(() -> new ResourceNotFoundException("StudentClass"));
    }
    private void apply(StudentClass e, StudentClassRequest r) {
        var program = programs.findById(r.programId())
                .orElseThrow(() -> new ResourceNotFoundException("Program"));
        var major = program.getMajor();
        if (r.majorId() != null && !r.majorId().equals(major.getId()))
            throw new IllegalArgumentException("Major must match the selected program");
        boolean changedProgram = e.getId() != null
                && (e.getProgram() == null || !e.getProgram().getId().equals(program.getId()));
        if ((e.getId() == null || changedProgram || r.active()) && (!major.isActive() || !program.isActive() || !major.getFaculty().isActive()))
            throw new IllegalArgumentException("Program, major and faculty must be active");
        if (changedProgram && students.existsByStudentClassId(e.getId()))
            throw new IllegalStateException("Cannot change the program of a class in use; transfer students first");
        int cohort = codes.cohort(program.getCohort());
        if (r.cohort() != null && r.cohort() != cohort)
            throw new IllegalArgumentException("Class cohort must match the program");
        if (e.getId() == null || changedProgram || !java.util.Objects.equals(e.getCohort(), cohort))
            e.setClassCode(codes.studentClass(major, cohort));
        e.setMajor(major);
        e.setProgram(program);
        e.setCohort(cohort);
        e.setAcademicYear(optional(r.academicYear()));

        e.setClassName(optional(r.name()));
        e.setActive(r.active());
    }
}
