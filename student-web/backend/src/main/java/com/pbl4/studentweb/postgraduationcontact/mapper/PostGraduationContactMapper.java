package com.pbl4.studentweb.postgraduationcontact.mapper;

import com.pbl4.studentweb.postgraduationcontact.entity.PostGraduationContact;
import com.pbl4.studentweb.postgraduationcontact.dto.PostGraduationContactSummary;
import org.springframework.stereotype.Component;

@Component
public class PostGraduationContactMapper {
    public PostGraduationContactSummary toSummary(PostGraduationContact e) {
        return new PostGraduationContactSummary(e.getId(), e.getStudent().getId());
    }
}
