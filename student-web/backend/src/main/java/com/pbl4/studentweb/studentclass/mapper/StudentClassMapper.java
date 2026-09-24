package com.pbl4.studentweb.studentclass.mapper;

import com.pbl4.studentweb.studentclass.entity.StudentClass;
import com.pbl4.studentweb.studentclass.dto.StudentClassSummary;
import org.springframework.stereotype.Component;

@Component
public class StudentClassMapper {
    public StudentClassSummary toSummary(StudentClass e) {
        return new StudentClassSummary(e.getId(), e.getClassCode(), e.getClassName(), e.getMajor().getId(), e.isActive());
    }
}
