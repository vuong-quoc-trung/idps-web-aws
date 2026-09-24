package com.pbl4.studentweb.student.dto;

import com.pbl4.studentweb.student.entity.ProfileStatus;
import java.util.List;
public record ProfileCompletionResult(ProfileStatus status, List<String> missingFields) {
    public ProfileCompletionResult { missingFields = List.copyOf(missingFields); }
}
