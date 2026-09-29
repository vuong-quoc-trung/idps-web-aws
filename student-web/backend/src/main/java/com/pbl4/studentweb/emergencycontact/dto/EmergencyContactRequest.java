package com.pbl4.studentweb.emergencycontact.dto;

import com.pbl4.studentweb.emergencycontact.entity.*;
import java.time.LocalDate;
import jakarta.validation.constraints.*;

/** Full replacement; optional fields may be cleared while a profile is incomplete. */
public record EmergencyContactRequest(@NotBlank @Size(max = 120) String fullName,
        @Size(max = 50) String relationship,
        @NotBlank @Size(max = 20) String phoneNumber,
        @Size(max = 255) String address,
        @NotNull @Positive Integer priority) {}
