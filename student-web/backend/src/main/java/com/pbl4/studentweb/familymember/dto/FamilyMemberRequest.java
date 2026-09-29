package com.pbl4.studentweb.familymember.dto;

import com.pbl4.studentweb.familymember.entity.*;
import java.time.LocalDate;
import jakarta.validation.constraints.*;

/** Full replacement; optional fields may be cleared while a profile is incomplete. */
public record FamilyMemberRequest(@NotNull FamilyRelationship relationship,
        @Size(max = 120) String fullName,
        @Past LocalDate dateOfBirth,
        @NotNull Boolean hasCollegeDegree,
        @NotNull Boolean unavailable,
        @Size(max = 20) String phoneNumber) {}
