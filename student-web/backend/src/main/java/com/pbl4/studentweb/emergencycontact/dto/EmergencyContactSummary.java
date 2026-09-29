package com.pbl4.studentweb.emergencycontact.dto;

import com.pbl4.studentweb.emergencycontact.entity.*;
import java.time.LocalDate;

public record EmergencyContactSummary(Long id, Long studentId, String fullName, String relationship, String phoneNumber, String address, Integer priority) {}
