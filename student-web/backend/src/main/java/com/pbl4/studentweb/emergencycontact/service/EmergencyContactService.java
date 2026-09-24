package com.pbl4.studentweb.emergencycontact.service;

import com.pbl4.studentweb.emergencycontact.repository.EmergencyContactRepository;
import com.pbl4.studentweb.emergencycontact.mapper.EmergencyContactMapper;
import com.pbl4.studentweb.emergencycontact.dto.EmergencyContactSummary;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class EmergencyContactService {
    private final EmergencyContactRepository repository;
    private final EmergencyContactMapper mapper;

    // Internal service only; caller authorization belongs to the future API layer.
    public Page<EmergencyContactSummary> findAll(Pageable pageable) {
        return repository.findAll(pageable).map(mapper::toSummary);
    }
}
