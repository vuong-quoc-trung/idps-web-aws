package com.pbl4.studentweb.studentaddress.mapper;

import com.pbl4.studentweb.studentaddress.entity.StudentAddress;
import com.pbl4.studentweb.studentaddress.dto.StudentAddressSummary;
import org.springframework.stereotype.Component;

@Component
public class StudentAddressMapper {
    public StudentAddressSummary toSummary(StudentAddress e) {
        return new StudentAddressSummary(e.getId(), e.getStudent().getId(), e.getAddressType(), e.getAddressLine(), e.getProvinceCity(), e.getWardCommune(), e.getResidenceRelation(), e.isCurrent(), e.getCountryCode());
    }
}
