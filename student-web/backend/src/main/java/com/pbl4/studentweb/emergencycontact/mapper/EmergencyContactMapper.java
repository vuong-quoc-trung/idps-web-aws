package com.pbl4.studentweb.emergencycontact.mapper;

import com.pbl4.studentweb.emergencycontact.entity.EmergencyContact;
import com.pbl4.studentweb.emergencycontact.dto.EmergencyContactSummary;
import org.springframework.stereotype.Component;

@Component
public class EmergencyContactMapper {
    public EmergencyContactSummary toSummary(EmergencyContact e) {
        return new EmergencyContactSummary(e.getId(), e.getStudent().getId());
    }
}
