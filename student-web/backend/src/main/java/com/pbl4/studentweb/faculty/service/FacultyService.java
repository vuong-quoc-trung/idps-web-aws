package com.pbl4.studentweb.faculty.service;

import com.pbl4.studentweb.faculty.repository.FacultyRepository;
import com.pbl4.studentweb.faculty.mapper.FacultyMapper;
import com.pbl4.studentweb.faculty.entity.Faculty;
import com.pbl4.studentweb.faculty.dto.*;
import com.pbl4.studentweb.common.exception.ResourceNotFoundException;
import com.pbl4.studentweb.major.repository.MajorRepository;
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
public class FacultyService {
    private final com.pbl4.studentweb.common.code.CodeGenerationService codes;
    private final FacultyRepository repository;
    private final FacultyMapper mapper;
    private final MajorRepository majors;

    public Page<FacultySummary> findAll(Pageable pageable) {
        return repository.findAll(pageable).map(mapper::toSummary);
    }
    public FacultySummary findById(Long id) { return mapper.toSummary(require(id)); }

    @Transactional
    public FacultySummary create(@NotNull @Valid FacultyRequest request) {
        if (repository.existsByFacultyCode(codes.faculty(request.shortCode()))) throw new IllegalStateException("Code already exists");
        var entity = new Faculty();
        apply(entity, request);
        return mapper.toSummary(repository.saveAndFlush(entity));
    }

    @Transactional
    public FacultySummary update(Long id, @NotNull @Valid FacultyRequest request) {
        var entity = require(id);
        if (repository.existsByFacultyCodeAndIdNot(codes.faculty(request.shortCode()), id)) throw new IllegalStateException("Code already exists");
        apply(entity, request);
        return mapper.toSummary(repository.saveAndFlush(entity));
    }

    @Transactional
    public void delete(Long id) {
        var entity = require(id);
        if (majors.existsByFacultyId(id)) throw new IllegalStateException("Catalog is in use; deactivate it instead");
        repository.delete(entity);
        repository.flush();
    }

    private Faculty require(Long id) {
        return repository.findById(id).orElseThrow(() -> new ResourceNotFoundException("Faculty"));
    }
    private void apply(Faculty e, FacultyRequest r) {
        e.setDescription(optional(r.description()));
        e.setShortCode(codes.normalizeShortCode(r.shortCode()));
        e.setFacultyCode(codes.faculty(r.shortCode()));
        e.setFacultyName(optional(r.name()));
        e.setActive(r.active());
    }
}
