package com.pbl4.studentweb.studentaddress.service;

import com.pbl4.studentweb.studentaddress.repository.StudentAddressRepository;
import com.pbl4.studentweb.studentaddress.mapper.StudentAddressMapper;
import com.pbl4.studentweb.studentaddress.dto.StudentAddressSummary;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class StudentAddressService {
    private final StudentAddressRepository repository;
    private final StudentAddressMapper mapper;

    // Internal service only; caller authorization belongs to the future API layer.
    public Page<StudentAddressSummary> findAll(Pageable pageable) {
        return repository.findAll(pageable).map(mapper::toSummary);
    }
}
