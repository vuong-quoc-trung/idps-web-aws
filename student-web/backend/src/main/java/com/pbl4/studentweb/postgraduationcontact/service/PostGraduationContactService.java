package com.pbl4.studentweb.postgraduationcontact.service;

import com.pbl4.studentweb.postgraduationcontact.repository.PostGraduationContactRepository;
import com.pbl4.studentweb.postgraduationcontact.mapper.PostGraduationContactMapper;
import com.pbl4.studentweb.postgraduationcontact.dto.PostGraduationContactSummary;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class PostGraduationContactService {
    private final PostGraduationContactRepository repository;
    private final PostGraduationContactMapper mapper;

    // Internal service only; caller authorization belongs to the future API layer.
    public Page<PostGraduationContactSummary> findAll(Pageable pageable) {
        return repository.findAll(pageable).map(mapper::toSummary);
    }
}
