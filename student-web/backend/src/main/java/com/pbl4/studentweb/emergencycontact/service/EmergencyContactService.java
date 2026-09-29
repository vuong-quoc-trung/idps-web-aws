package com.pbl4.studentweb.emergencycontact.service;

import com.pbl4.studentweb.emergencycontact.repository.EmergencyContactRepository;
import com.pbl4.studentweb.emergencycontact.mapper.EmergencyContactMapper;
import com.pbl4.studentweb.emergencycontact.entity.EmergencyContact;
import com.pbl4.studentweb.emergencycontact.dto.*;
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
public class EmergencyContactService {
    private final EmergencyContactRepository repository;
    private final EmergencyContactMapper mapper;
    private final StudentRepository students;
    private final StudentProfileCompletionService completion;

    // Internal operation; the API exposes only student-scoped reads.
    public Page<EmergencyContactSummary> findAll(Pageable pageable) {
        return repository.findAll(pageable).map(mapper::toSummary);
    }
    public List<EmergencyContactSummary> findByStudentId(Long studentId) {
        if (!students.existsById(studentId)) throw new ResourceNotFoundException("Student");
        return repository.findByStudentId(studentId).stream().map(mapper::toSummary).toList();
    }
    public EmergencyContactSummary findById(Long studentId, Long id) { return mapper.toSummary(require(studentId, id)); }

    @Transactional
    public EmergencyContactSummary create(Long studentId, @NotNull @Valid EmergencyContactRequest request) {
        var student = students.findById(studentId).orElseThrow(() -> new ResourceNotFoundException("Student"));
        var entity = new EmergencyContact();
        entity.setStudent(student);
        apply(entity, request);
        repository.saveAndFlush(entity);
        completion.refresh(studentId);
        return mapper.toSummary(entity);
    }
    @Transactional
    public EmergencyContactSummary update(Long studentId, Long id, @NotNull @Valid EmergencyContactRequest request) {
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
    private EmergencyContact require(Long studentId, Long id) {
        return repository.findByIdAndStudentId(id, studentId)
                .orElseThrow(() -> new ResourceNotFoundException("EmergencyContact"));
    }
    private void apply(EmergencyContact e, EmergencyContactRequest r) {
        e.setFullName(optional(r.fullName()));
        e.setRelationship(optional(r.relationship()));
        e.setPhoneNumber(optional(r.phoneNumber()));
        e.setAddress(optional(r.address()));
        e.setPriority(r.priority());
    }
}
