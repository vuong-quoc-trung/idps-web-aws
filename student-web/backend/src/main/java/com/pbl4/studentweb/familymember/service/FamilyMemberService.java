package com.pbl4.studentweb.familymember.service;

import com.pbl4.studentweb.familymember.repository.FamilyMemberRepository;
import com.pbl4.studentweb.familymember.mapper.FamilyMemberMapper;
import com.pbl4.studentweb.familymember.entity.FamilyMember;
import com.pbl4.studentweb.familymember.dto.*;
import com.pbl4.studentweb.student.repository.StudentRepository;
import com.pbl4.studentweb.student.service.StudentProfileCompletionService;
import com.pbl4.studentweb.common.exception.ResourceNotFoundException;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import static com.pbl4.studentweb.common.validation.TextValues.optional;

@Service
@Validated
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class FamilyMemberService {
    private final FamilyMemberRepository repository;
    private final FamilyMemberMapper mapper;
    private final StudentRepository students;
    private final StudentProfileCompletionService completion;

    // Internal operation; the API exposes only student-scoped reads.
    public Page<FamilyMemberSummary> findAll(Pageable pageable) {
        return repository.findAll(pageable).map(mapper::toSummary);
    }
    public List<FamilyMemberSummary> findByStudentId(Long studentId) {
        if (!students.existsById(studentId)) throw new ResourceNotFoundException("Student");
        return repository.findByStudentId(studentId).stream().map(mapper::toSummary).toList();
    }
    public FamilyMemberSummary findById(Long studentId, Long id) { return mapper.toSummary(require(studentId, id)); }

    @Transactional
    public FamilyMemberSummary create(Long studentId, @NotNull @Valid FamilyMemberRequest request) {
        var student = students.findById(studentId).orElseThrow(() -> new ResourceNotFoundException("Student"));
        var entity = new FamilyMember();
        entity.setStudent(student);
        apply(entity, request);
        repository.saveAndFlush(entity);
        completion.refresh(studentId);
        return mapper.toSummary(entity);
    }
    @Transactional
    public FamilyMemberSummary update(Long studentId, Long id, @NotNull @Valid FamilyMemberRequest request) {
        var entity = require(studentId, id);
        apply(entity, request);
        repository.saveAndFlush(entity);
        completion.refresh(studentId);
        return mapper.toSummary(entity);
    }
    @Transactional
    public void delete(Long studentId, Long id) {
        repository.delete(require(studentId, id));
        repository.flush();
        completion.refresh(studentId);
    }
    private FamilyMember require(Long studentId, Long id) {
        return repository.findByIdAndStudentId(id, studentId)
                .orElseThrow(() -> new ResourceNotFoundException("FamilyMember"));
    }
    private void apply(FamilyMember e, FamilyMemberRequest r) {
        e.setRelationship(r.relationship());
        e.setFullName(optional(r.fullName()));
        e.setDateOfBirth(r.dateOfBirth());
        e.setHasCollegeDegree(r.hasCollegeDegree());
        e.setUnavailable(r.unavailable());
        e.setPhoneNumber(optional(r.phoneNumber()));
    }
}
