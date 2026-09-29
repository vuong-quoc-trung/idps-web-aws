package com.pbl4.studentweb.postgraduationcontact.dto;

import com.pbl4.studentweb.postgraduationcontact.entity.*;
import java.time.LocalDate;

public record PostGraduationContactSummary(Long id, Long studentId, String fullName, String phoneNumber, String email, String address) {}
