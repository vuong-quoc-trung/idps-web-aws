package com.pbl4.studentweb.postgraduationcontact.service;

import com.pbl4.studentweb.postgraduationcontact.repository.PostGraduationContactRepository;
import com.pbl4.studentweb.postgraduationcontact.mapper.PostGraduationContactMapper;
import com.pbl4.studentweb.postgraduationcontact.entity.PostGraduationContact;
import com.pbl4.studentweb.postgraduationcontact.dto.*;
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
public class PostGraduationContactService {
    private final PostGraduationContactRepository repository;
    private final PostGraduationContactMapper mapper;
    private final StudentRepository students;
    private final StudentProfileCompletionService completion;

    // Internal operation; the API exposes only student-scoped reads.
    public Page<PostGraduationContactSummary> findAll(Pageable pageable) {
        return repository.findAll(pageable).map(mapper::toSummary);
    }
    public List<PostGraduationContactSummary> findByStudentId(Long studentId) {
        if (!students.existsById(studentId)) throw new ResourceNotFoundException("Student");
        return repository.findByStudentId(studentId).stream().map(mapper::toSummary).toList();
    }
    public PostGraduationContactSummary findById(Long studentId, Long id) { return mapper.toSummary(require(studentId, id)); }

    @Transactional
    public PostGraduationContactSummary create(Long studentId, @NotNull @Valid PostGraduationContactRequest request) {
        var student = students.findById(studentId).orElseThrow(() -> new ResourceNotFoundException("Student"));
        var entity = new PostGraduationContact();
        entity.setStudent(student);
        apply(entity, request);
        repository.saveAndFlush(entity);
        completion.refresh(studentId);
        return mapper.toSummary(entity);
    }
    @Transactional
    public PostGraduationContactSummary update(Long studentId, Long id, @NotNull @Valid PostGraduationContactRequest request) {
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
    private PostGraduationContact require(Long studentId, Long id) {
        return repository.findByIdAndStudentId(id, studentId)
                .orElseThrow(() -> new ResourceNotFoundException("PostGraduationContact"));
    }
    private void apply(PostGraduationContact e, PostGraduationContactRequest r) {
        e.setFullName(optional(r.fullName()));
        e.setPhoneNumber(optional(r.phoneNumber()));
        e.setEmail(optional(r.email()));
        e.setAddress(optional(r.address()));
    }
}
