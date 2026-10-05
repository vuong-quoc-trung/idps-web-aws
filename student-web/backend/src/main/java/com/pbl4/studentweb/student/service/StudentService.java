package com.pbl4.studentweb.student.service;

import com.pbl4.studentweb.common.exception.ResourceNotFoundException;
import com.pbl4.studentweb.student.dto.*;
import com.pbl4.studentweb.student.entity.*;
import com.pbl4.studentweb.student.mapper.StudentMapper;
import com.pbl4.studentweb.student.repository.StudentRepository;
import com.pbl4.studentweb.trainingprogram.repository.TrainingProgramRepository;
import com.pbl4.studentweb.trainingprogram.entity.TrainingProgram;
import jakarta.persistence.criteria.Predicate;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import java.util.ArrayList;
import java.util.Locale;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;
import static com.pbl4.studentweb.common.validation.TextValues.optional;

@Service
@Validated
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class StudentService {
    private final StudentRepository students;
    private final StudentMapper mapper;
    private final StudentAcademicAssignment academicAssignment;
    private final TrainingProgramRepository programs;
    private final StudentProfileCompletionService completion;

    public Page<StudentSummary> findAll(String search, Long majorId, Long classId, StudentStatus status, Pageable page) {
        String query = optional(search);
        if (query != null && query.length() > 120) throw new IllegalArgumentException("Search is too long");
        Specification<Student> filter = (root, criteria, cb) -> {
            var predicates = new ArrayList<Predicate>();
            if (query != null) {
                String pattern = "%" + query.toLowerCase(Locale.ROOT).replace("!", "!!")
                        .replace("%", "!%").replace("_", "!_") + "%";
                predicates.add(cb.or(cb.like(cb.lower(root.get("studentCode")), pattern, '!'),
                        cb.like(cb.lower(root.get("fullName")), pattern, '!')));
            }
            if (majorId != null) predicates.add(cb.equal(root.get("major").get("id"), majorId));
            if (classId != null) predicates.add(cb.equal(root.get("studentClass").get("id"), classId));
            if (status != null) predicates.add(cb.equal(root.get("status"), status));
            return cb.and(predicates.toArray(Predicate[]::new));
        };
        return students.findAll(filter, page).map(mapper::toSummary);
    }

    public StudentDetail findById(Long id) { return mapper.toDetail(require(id)); }

    @Transactional
    public StudentDetail update(Long id, @NotNull @Valid UpdateStudentRequest r) {
        var s = require(id);
        boolean changingClass = !s.getStudentClass().getId().equals(r.classId());
        // Editing existing records remains possible after catalogs are deactivated.
        var studentClass = academicAssignment.resolve(r.classId(), r.majorId(), r.trainingProgramId(), changingClass);
        var primary = studentClass.getProgram();
        var major = primary.getMajor();
        var secondary = r.secondaryProgramId() == null ? null : program(r.secondaryProgramId(), s.getSecondaryProgram());
        String citizen = optional(r.citizenId());
        if (citizen != null && students.existsByCitizenIdAndIdNot(citizen, id))
            throw new IllegalStateException("Citizen ID already exists");
        s.setFullName(r.fullName().trim());
        s.setDateOfBirth(r.dateOfBirth());
        s.setGender(r.gender());
        s.setCitizenId(citizen);
        s.setMajor(major);
        s.setStudentClass(studentClass);
        s.setTrainingProgram(primary);
        s.setSecondaryProgram(secondary);
        s.setFamilyPhoneNumber(com.pbl4.studentweb.common.validation.ContactValues.phone(r.familyPhoneNumber()));
        s.setBankAccountNumber(optional(r.bankAccountNumber()));
        s.setBankName(optional(r.bankName()));
        s.setStatus(r.status());
        if (r.status() == StudentStatus.INACTIVE || r.status() == StudentStatus.SUSPENDED) s.getUser().setEnabled(false);
        completion.refresh(id);
        students.flush();
        return mapper.toDetail(s);
    }

    /** Archive the student and disable sign-in; retain contacts and security logs. */
    @Transactional
    public void delete(Long id) {
        var s = require(id);
        s.setStatus(StudentStatus.INACTIVE);
        s.getUser().setEnabled(false);
        s.getUser().setActivationTokenHash(null);
        s.getUser().setActivationExpiresAt(null);
    }

    private Student require(Long id) {
        return students.findById(id).orElseThrow(() -> new ResourceNotFoundException("Student"));
    }
    private TrainingProgram program(Long id, TrainingProgram current) {
        var p = programs.findById(id).orElseThrow(() -> new ResourceNotFoundException("Program"));
        if ((current == null || !current.getId().equals(id)) && (!p.isActive() || !p.getMajor().isActive() || !p.getMajor().getFaculty().isActive()))
            throw new IllegalArgumentException("New program assignment must be active");
        return p;
    }
}
