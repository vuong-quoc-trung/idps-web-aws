package com.pbl4.studentweb.familymember.dto;

import com.pbl4.studentweb.familymember.entity.*;
import java.time.LocalDate;

public record FamilyMemberSummary(Long id, Long studentId, FamilyRelationship relationship, String fullName, LocalDate dateOfBirth, Boolean hasCollegeDegree, Boolean unavailable, String phoneNumber) {}
