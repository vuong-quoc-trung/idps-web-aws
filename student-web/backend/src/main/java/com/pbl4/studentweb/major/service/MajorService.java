package com.pbl4.studentweb.major.service;

import com.pbl4.studentweb.major.repository.MajorRepository;
import com.pbl4.studentweb.major.mapper.MajorMapper;
import com.pbl4.studentweb.major.dto.MajorSummary;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class MajorService {
    private final MajorRepository repository;
    private final MajorMapper mapper;

    // Internal service only; caller authorization belongs to the future API layer.
    public Page<MajorSummary> findAll(Pageable pageable) {
        return repository.findAll(pageable).map(mapper::toSummary);
    }
}
