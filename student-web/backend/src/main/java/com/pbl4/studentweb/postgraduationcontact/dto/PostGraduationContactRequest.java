package com.pbl4.studentweb.postgraduationcontact.dto;

import com.pbl4.studentweb.postgraduationcontact.entity.*;
import java.time.LocalDate;
import jakarta.validation.constraints.*;
import com.pbl4.studentweb.common.validation.PhoneNumber;
import com.pbl4.studentweb.common.validation.ContactEmail;

/** Full replacement; optional fields may be cleared while a profile is incomplete. */
public record PostGraduationContactRequest(@Size(max = 120) String fullName,
        @PhoneNumber String phoneNumber,
        @ContactEmail String email,
        @Size(max = 255) String address) {}
