package com.pbl4.studentweb.postgraduationcontact.dto;

import com.pbl4.studentweb.postgraduationcontact.entity.*;
import java.time.LocalDate;
import jakarta.validation.constraints.*;

/** Full replacement; optional fields may be cleared while a profile is incomplete. */
public record PostGraduationContactRequest(@Size(max = 120) String fullName,
        @Size(max = 20) String phoneNumber,
        @Email @Size(max = 150) String email,
        @Size(max = 255) String address) {}
