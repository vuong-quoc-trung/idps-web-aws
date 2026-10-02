package com.pbl4.studentweb.student.service;

import com.pbl4.studentweb.student.dto.*;
import com.pbl4.studentweb.student.entity.Student;
import com.pbl4.studentweb.student.mapper.StudentMapper;
import com.pbl4.studentweb.student.repository.StudentRepository;
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
    private final com.pbl4.studentweb.common.code.CodeGenerationService codes;
    private final StudentRepository students;
    private final UserRepository users;
    private final StudentAcademicAssignment academicAssignment;
    private final TrainingProgramRepository programs;
    private final PasswordSetupService passwords;
    private final StudentMapper mapper;

    // Invoked by the ADMIN/STAFF student API. All academic links are checked before account creation.
    @Transactional
    public StudentOnboardingResult create(@NotNull @Valid CreateStudentRequest r) {
        var studentClass = academicAssignment.resolve(r.classId(), r.majorId(), r.trainingProgramId(), true);
        var program = studentClass.getProgram();
        var major = program.getMajor();
        var secondary = r.secondaryProgramId() == null ? null : program(r.secondaryProgramId());
        String code = codes.student(studentClass.getCohort());
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
        s.setSecondaryProgram(secondary);
        s.setSchoolEmail(blankToNull(r.schoolEmail()));
        s.setFamilyPhoneNumber(blankToNull(r.familyPhoneNumber()));
        return new StudentOnboardingResult(mapper.toSummary(students.saveAndFlush(s)), token);
    }

    private TrainingProgram program(Long id) {
        var p = programs.findById(id).orElseThrow(() -> new ResourceNotFoundException("Program"));
        if (!p.isActive() || !p.getMajor().isActive() || !p.getMajor().getFaculty().isActive()) throw new IllegalArgumentException("Program is inactive");
        return p;
    }
    private String blankToNull(String value) { return value == null || value.isBlank() ? null : value.trim(); }
}
