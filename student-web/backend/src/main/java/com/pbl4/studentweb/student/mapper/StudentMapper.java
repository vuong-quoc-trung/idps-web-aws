package com.pbl4.studentweb.student.mapper;

import com.pbl4.studentweb.student.entity.Student;
import com.pbl4.studentweb.student.dto.StudentSummary;
import org.springframework.stereotype.Component;
@Component
public class StudentMapper {
    public StudentSummary toSummary(Student s) {
        return new StudentSummary(s.getId(), s.getStudentCode(), s.getFullName(),
                s.getMajor().getId(), s.getStudentClass().getId(), s.getProfileStatus());
    }
}
