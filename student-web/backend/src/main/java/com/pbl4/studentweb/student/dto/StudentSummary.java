package com.pbl4.studentweb.student.dto;

import com.pbl4.studentweb.student.entity.ProfileStatus;

public record StudentSummary(Long id, String studentCode, String fullName, Long majorId,
                             Long classId, ProfileStatus profileStatus) {}
