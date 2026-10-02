package com.pbl4.studentweb.faculty.mapper;

import com.pbl4.studentweb.faculty.dto.FacultySummary;
import com.pbl4.studentweb.faculty.entity.Faculty;
import org.springframework.stereotype.Component;

@Component
public class FacultyMapper {
    public FacultySummary toSummary(Faculty e) {
        return new FacultySummary(e.getId(), e.getFacultyCode(), e.getShortCode(), e.getFacultyName(), e.getDescription(), e.isActive());
    }
}
