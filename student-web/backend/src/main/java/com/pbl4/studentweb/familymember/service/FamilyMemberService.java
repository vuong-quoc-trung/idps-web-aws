package com.pbl4.studentweb.familymember.service;

import com.pbl4.studentweb.familymember.repository.FamilyMemberRepository;
import com.pbl4.studentweb.familymember.mapper.FamilyMemberMapper;
import com.pbl4.studentweb.familymember.dto.FamilyMemberSummary;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class FamilyMemberService {
    private final FamilyMemberRepository repository;
    private final FamilyMemberMapper mapper;

    // Internal service only; caller authorization belongs to the future API layer.
    public Page<FamilyMemberSummary> findAll(Pageable pageable) {
        return repository.findAll(pageable).map(mapper::toSummary);
    }
}
