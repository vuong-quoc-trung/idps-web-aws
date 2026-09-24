package com.pbl4.studentweb.familymember.mapper;

import com.pbl4.studentweb.familymember.entity.FamilyMember;
import com.pbl4.studentweb.familymember.dto.FamilyMemberSummary;
import org.springframework.stereotype.Component;

@Component
public class FamilyMemberMapper {
    public FamilyMemberSummary toSummary(FamilyMember e) {
        return new FamilyMemberSummary(e.getId(), e.getStudent().getId());
    }
}
