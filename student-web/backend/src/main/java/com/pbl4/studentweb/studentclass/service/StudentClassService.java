package com.pbl4.studentweb.studentclass.service;

import com.pbl4.studentweb.studentclass.repository.StudentClassRepository;
import com.pbl4.studentweb.studentclass.mapper.StudentClassMapper;
import com.pbl4.studentweb.studentclass.dto.StudentClassSummary;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class StudentClassService {
    private final StudentClassRepository repository;
    private final StudentClassMapper mapper;

    // Internal service only; caller authorization belongs to the future API layer.
    public Page<StudentClassSummary> findAll(Pageable pageable) {
        return repository.findAll(pageable).map(mapper::toSummary);
    }
}
