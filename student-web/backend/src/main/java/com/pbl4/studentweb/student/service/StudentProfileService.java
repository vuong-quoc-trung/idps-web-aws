package com.pbl4.studentweb.student.service;

import com.pbl4.studentweb.student.dto.*;
import com.pbl4.studentweb.student.repository.StudentRepository;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
@RequiredArgsConstructor
public class StudentProfileService {
    private final StudentRepository students;
    private final StudentProfileCompletionService completion;

    /** Full replacement of white personal fields. userId MUST come from the authenticated principal. */
    @Transactional
    public ProfileCompletionResult updateForUser(Long authenticatedUserId, @Valid UpdateStudentProfileRequest r) {
        var s = students.findByUserId(authenticatedUserId).orElseThrow(() -> new IllegalArgumentException("Student not found"));
        if (!s.getUser().isEnabled() || s.getUser().isPasswordSetupRequired())
            throw new IllegalStateException("Set the initial password before updating the profile");
        s.setAvatarUrl(r.avatarUrl());
        s.setPlaceOfBirth(r.placeOfBirth());
        s.setOldPlaceOfBirth(r.oldPlaceOfBirth());
        s.setEthnicity(r.ethnicity());
        s.setNationality(r.nationality());
        s.setReligion(r.religion());
        s.setCitizenIdIssueDate(r.citizenIdIssueDate());
        s.setHealthInsuranceNumber(r.healthInsuranceNumber());
        s.setHealthInsuranceExpiry(r.healthInsuranceExpiry());
        s.setFreeHealthInsurance(r.freeHealthInsurance());
        s.setPersonalEmail(r.personalEmail());
        s.setPhoneNumber(r.phoneNumber());
        s.setFacebookUrl(r.facebookUrl());
        return completion.refresh(s.getId());
    }
}
