package com.pbl4.studentweb.major.mapper;

import com.pbl4.studentweb.major.entity.Major;
import com.pbl4.studentweb.major.dto.MajorSummary;
import org.springframework.stereotype.Component;

@Component
public class MajorMapper {
    public MajorSummary toSummary(Major e) {
        return new MajorSummary(e.getId(), e.getMajorCode(), e.getMajorName(), e.isActive());
    }
}
