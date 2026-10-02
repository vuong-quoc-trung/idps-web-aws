package com.pbl4.studentweb.major.service;

import com.pbl4.studentweb.major.repository.MajorRepository;
import com.pbl4.studentweb.major.mapper.MajorMapper;
import com.pbl4.studentweb.major.entity.Major;
import com.pbl4.studentweb.major.dto.*;
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
public class MajorService {
    private final com.pbl4.studentweb.common.code.CodeGenerationService codes;
    private final MajorRepository repository;
    private final MajorMapper mapper;
    private final com.pbl4.studentweb.faculty.repository.FacultyRepository faculties;
    private final StudentRepository students;
    private final com.pbl4.studentweb.studentclass.repository.StudentClassRepository classes;
    private final com.pbl4.studentweb.trainingprogram.repository.TrainingProgramRepository programs;

    public Page<MajorSummary> findAll(Pageable pageable) {
        return repository.findAll(pageable).map(mapper::toSummary);
    }
    public MajorSummary findById(Long id) { return mapper.toSummary(require(id)); }

    @Transactional
    public MajorSummary create(@NotNull @Valid MajorRequest request) {
        if (repository.existsByMajorCode(codes.major(request.shortCode()))) throw new IllegalStateException("Code already exists");
        var entity = new Major();
        apply(entity, request);
        return mapper.toSummary(repository.saveAndFlush(entity));
    }

    @Transactional
    public MajorSummary update(Long id, @NotNull @Valid MajorRequest request) {
        var entity = require(id);
        if (repository.existsByMajorCodeAndIdNot(codes.major(request.shortCode()), id)) throw new IllegalStateException("Code already exists");
        apply(entity, request);
        return mapper.toSummary(repository.saveAndFlush(entity));
    }

    @Transactional
    public void delete(Long id) {
        var entity = require(id);
        if (students.existsByMajorId(id) || classes.existsByMajorId(id) || programs.existsByMajorId(id)) throw new IllegalStateException("Catalog is in use; deactivate it instead");
        repository.delete(entity);
        repository.flush();
    }

    private Major require(Long id) {
        return repository.findById(id).orElseThrow(() -> new ResourceNotFoundException("Major"));
    }
    private void apply(Major e, MajorRequest r) {
        var faculty = faculties.findById(r.facultyId()).orElseThrow(() -> new ResourceNotFoundException("Faculty"));
        boolean changedFaculty = e.getId() != null && !e.getFaculty().getId().equals(faculty.getId());
        if ((e.getId() == null || changedFaculty || r.active()) && !faculty.isActive())
            throw new IllegalArgumentException("Faculty is inactive");
        if (changedFaculty && (programs.existsByMajorId(e.getId())
                || classes.existsByMajorId(e.getId()) || students.existsByMajorId(e.getId())))
            throw new IllegalStateException("Cannot change the faculty of a major in use");
        if (e.getId() != null && e.getShortCode() != null
                && !e.getShortCode().equals(codes.normalizeShortCode(r.shortCode()))
                && (programs.existsByMajorId(e.getId()) || classes.existsByMajorId(e.getId()) || students.existsByMajorId(e.getId())))
            throw new IllegalStateException("Cannot change shortCode of a major in use");
        e.setFaculty(faculty);
        e.setDescription(optional(r.description()));
        e.setShortCode(codes.normalizeShortCode(r.shortCode()));
        e.setMajorCode(codes.major(r.shortCode()));
        e.setMajorName(optional(r.name()));
        e.setActive(r.active());
    }
}
