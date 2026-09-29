package com.pbl4.studentweb.student.service;

import com.pbl4.studentweb.common.exception.ResourceNotFoundException;
import com.pbl4.studentweb.studentclass.entity.StudentClass;
import com.pbl4.studentweb.studentclass.repository.StudentClassRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Resolves the required Class -> Program -> Major chain for both creation and transfer. */
@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class StudentAcademicAssignment {
    private final StudentClassRepository classes;

    public StudentClass resolve(Long classId, Long expectedMajorId, Long expectedProgramId, boolean requireActive) {
        var group = classes.findById(classId).orElseThrow(() -> new ResourceNotFoundException("Class"));
        var program = group.getProgram();
        if (program == null)
            throw new IllegalStateException("Class has no training program; assign a program before adding students");
        var major = program.getMajor();
        if (major == null || group.getMajor() == null || !group.getMajor().getId().equals(major.getId()))
            throw new IllegalStateException("Class and program have inconsistent majors; repair the class first");
        if (expectedMajorId != null && !expectedMajorId.equals(major.getId()))
            throw new IllegalArgumentException("Major must match the selected class");
        if (expectedProgramId != null && !expectedProgramId.equals(program.getId()))
            throw new IllegalArgumentException("Primary program must match the selected class");
        if (requireActive && (!group.isActive() || !program.isActive() || !major.isActive() || !major.getFaculty().isActive()))
            throw new IllegalArgumentException("Class, program, major and faculty must all be active");
        return group;
    }
}
