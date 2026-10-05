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
    private final com.pbl4.studentweb.common.catalog.ProfileCatalogService catalogs;
    private final StudentRepository students;
    private final StudentProfileCompletionService completion;

    /** Full replacement of white personal fields. userId MUST come from the authenticated principal. */
    @Transactional
    public ProfileCompletionResult updateForUser(Long authenticatedUserId, @Valid UpdateStudentProfileRequest r) {
        var s = students.findByUserId(authenticatedUserId).orElseThrow(() -> new IllegalArgumentException("Student not found"));
        if (!s.getUser().isEnabled() || s.getUser().isPasswordSetupRequired())
            throw new IllegalStateException("Set the initial password before updating the profile");
        s.setAvatarUrl(r.avatarUrl());
        String birthCountry = catalogs.country(r.birthCountryCode());
        String originCountry = catalogs.country(r.originCountryCode());
        s.setPlaceOfBirth(catalogs.province(r.placeOfBirth(), birthCountry, false,
                birthCountry.equals(s.getBirthCountryCode()) ? s.getPlaceOfBirth() : null));
        s.setOldPlaceOfBirth(catalogs.province(r.oldPlaceOfBirth(), originCountry, true,
                originCountry.equals(s.getOriginCountryCode()) ? s.getOldPlaceOfBirth() : null));
        s.setBirthCountryCode(birthCountry);
        s.setOriginCountryCode(originCountry);
        s.setEthnicity(catalogs.choice(r.ethnicity(), catalogs.catalog().ethnicities(), s.getEthnicity(), "Dân tộc"));
        s.setNationality(catalogs.choice(r.nationality(), catalogs.catalog().countries().stream().map(c -> c.name()).toList(), s.getNationality(), "Quốc tịch"));
        s.setReligion(catalogs.choice(r.religion(), catalogs.catalog().religions(), s.getReligion(), "Tôn giáo"));
        s.setCitizenIdIssueDate(r.citizenIdIssueDate());
        s.setHealthInsuranceNumber(r.healthInsuranceNumber());
        s.setHealthInsuranceExpiry(r.healthInsuranceExpiry());
        s.setFreeHealthInsurance(r.freeHealthInsurance());
        s.setPersonalEmail(com.pbl4.studentweb.common.validation.TextValues.optional(r.personalEmail()));
        s.setPhoneNumber(com.pbl4.studentweb.common.validation.ContactValues.phone(r.phoneNumber()));
        s.setFacebookUrl(r.facebookUrl());
        return completion.refresh(s.getId());
    }
}
