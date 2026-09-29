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
    private final StudentClassRepository repository;
    private final StudentClassMapper mapper;
    private final StudentRepository students;
    private final com.pbl4.studentweb.major.repository.MajorRepository majors;
    private final com.pbl4.studentweb.trainingprogram.repository.TrainingProgramRepository programs;

    public Page<StudentClassSummary> findAll(Pageable pageable) {
        return repository.findAll(pageable).map(mapper::toSummary);
    }
    public StudentClassSummary findById(Long id) { return mapper.toSummary(require(id)); }

    @Transactional
    public StudentClassSummary create(@NotNull @Valid StudentClassRequest request) {
        if (repository.existsByClassCode(request.code().trim())) throw new IllegalStateException("Code already exists");
        var entity = new StudentClass();
        apply(entity, request);
        return mapper.toSummary(repository.saveAndFlush(entity));
    }

    @Transactional
    public StudentClassSummary update(Long id, @NotNull @Valid StudentClassRequest request) {
        var entity = require(id);
        if (repository.existsByClassCodeAndIdNot(request.code().trim(), id)) throw new IllegalStateException("Code already exists");
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
        var major = majors.findById(r.majorId()).orElseThrow(() -> new ResourceNotFoundException("Major"));
        var program = r.programId() == null ? null : programs.findById(r.programId())
                .orElseThrow(() -> new ResourceNotFoundException("Program"));
        if (r.active() && !major.isActive()) throw new IllegalArgumentException("Major is inactive");
        if (program != null && (!program.getMajor().getId().equals(major.getId()) || (r.active() && !program.isActive())))
            throw new IllegalArgumentException("Program must belong to the selected major and be active for an active class");
        if (e.getId() != null && !e.getMajor().getId().equals(major.getId()) && students.existsByStudentClassId(e.getId()))
            throw new IllegalStateException("Cannot change the major of a class in use");
        e.setMajor(major);
        e.setProgram(program);
        e.setCohort(r.cohort());
        e.setAcademicYear(optional(r.academicYear()));
        e.setClassCode(r.code().trim());
        e.setClassName(optional(r.name()));
        e.setActive(r.active());
    }
}
