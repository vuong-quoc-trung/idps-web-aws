package com.pbl4.studentweb.student.service;

import com.pbl4.studentweb.student.dto.*;
import com.pbl4.studentweb.student.entity.Student;
import com.pbl4.studentweb.student.mapper.StudentMapper;
import com.pbl4.studentweb.student.repository.StudentRepository;
import com.pbl4.studentweb.major.repository.MajorRepository;
import com.pbl4.studentweb.studentclass.repository.StudentClassRepository;
import com.pbl4.studentweb.trainingprogram.entity.TrainingProgram;
import com.pbl4.studentweb.trainingprogram.repository.TrainingProgramRepository;
import com.pbl4.studentweb.user.entity.*;
import com.pbl4.studentweb.user.repository.UserRepository;
import com.pbl4.studentweb.user.service.PasswordSetupService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import com.pbl4.studentweb.common.exception.ResourceNotFoundException;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
@RequiredArgsConstructor
public class StudentOnboardingService {
    private final StudentRepository students;
    private final UserRepository users;
    private final MajorRepository majors;
    private final StudentClassRepository classes;
    private final TrainingProgramRepository programs;
    private final PasswordSetupService passwords;
    private final StudentMapper mapper;

    // Internal operation. Future controller must require ADMIN/STAFF authorization.
    @Transactional
    public StudentOnboardingResult create(@NotNull @Valid CreateStudentRequest r) {
        String code = r.studentCode().trim();
        if (students.existsByStudentCode(code) || users.existsByUsername(code))
            throw new IllegalStateException("Student code or username already exists");
        var major = majors.findById(r.majorId()).orElseThrow(() -> new ResourceNotFoundException("Major"));
        var studentClass = classes.findById(r.classId()).orElseThrow(() -> new ResourceNotFoundException("Class"));
        if (!major.isActive() || !studentClass.isActive() || !studentClass.getMajor().getId().equals(major.getId()))
            throw new IllegalArgumentException("Class must belong to the selected active major");
        TrainingProgram program = r.trainingProgramId() == null ? studentClass.getProgram() : program(r.trainingProgramId());
        if (program != null && (!program.isActive() || !program.getMajor().getId().equals(major.getId())))
            throw new IllegalArgumentException("Primary program must belong to the selected active major");
        User user = new User();
        user.setUsername(code);
        user.setRole(UserRole.STUDENT);
        String token = passwords.prepareNewAccount(user);
        users.save(user);
        Student s = new Student();
        s.setUser(user);
        s.setStudentCode(code);
        s.setFullName(r.fullName().trim());
        s.setDateOfBirth(r.dateOfBirth());
        s.setGender(r.gender());
        s.setCitizenId(blankToNull(r.citizenId()));
        s.setMajor(major);
        s.setStudentClass(studentClass);
        s.setTrainingProgram(program);
        if (r.secondaryProgramId() != null) s.setSecondaryProgram(program(r.secondaryProgramId()));
        s.setSchoolEmail(blankToNull(r.schoolEmail()));
        s.setFamilyPhoneNumber(blankToNull(r.familyPhoneNumber()));
        return new StudentOnboardingResult(mapper.toSummary(students.saveAndFlush(s)), token);
    }

    private TrainingProgram program(Long id) {
        var p = programs.findById(id).orElseThrow(() -> new ResourceNotFoundException("Program"));
        if (!p.isActive() || !p.getMajor().isActive()) throw new IllegalArgumentException("Program is inactive");
        return p;
    }
    private String blankToNull(String value) { return value == null || value.isBlank() ? null : value.trim(); }
}
