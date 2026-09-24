package com.pbl4.studentweb.student.service;

import com.pbl4.studentweb.student.dto.ProfileCompletionResult;
import com.pbl4.studentweb.student.entity.*;
import com.pbl4.studentweb.student.repository.StudentRepository;
import com.pbl4.studentweb.studentaddress.entity.*;
import com.pbl4.studentweb.studentaddress.repository.StudentAddressRepository;
import com.pbl4.studentweb.familymember.entity.*;
import com.pbl4.studentweb.familymember.repository.FamilyMemberRepository;
import com.pbl4.studentweb.emergencycontact.repository.EmergencyContactRepository;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
public class StudentProfileCompletionService {
    private final StudentRepository students;
    private final StudentAddressRepository addresses;
    private final FamilyMemberRepository family;
    private final EmergencyContactRepository emergency;

    @Transactional
    public ProfileCompletionResult refresh(Long studentId) {
        Student s = students.findById(studentId).orElseThrow(() -> new IllegalArgumentException("Student not found"));
        List<String> missing = new ArrayList<>();
        need(missing, "dateOfBirth", s.getDateOfBirth());
        need(missing, "gender", s.getGender());
        need(missing, "placeOfBirth", s.getPlaceOfBirth());
        need(missing, "ethnicity", s.getEthnicity());
        need(missing, "nationality", s.getNationality());
        need(missing, "citizenId", s.getCitizenId());
        need(missing, "citizenIdIssueDate", s.getCitizenIdIssueDate());
        // Free insurance still requires card details. Applicability exemptions need a separate future policy.
        need(missing, "healthInsuranceNumber", s.getHealthInsuranceNumber());
        need(missing, "healthInsuranceExpiry", s.getHealthInsuranceExpiry());
        need(missing, "trainingProgram", s.getTrainingProgram());
        need(missing, "personalEmail", s.getPersonalEmail());
        need(missing, "phoneNumber", s.getPhoneNumber());
        var validAddresses = addresses.findByStudentId(studentId).stream()
                .filter(a -> a.isCurrent() && present(a.getAddressLine()) && present(a.getProvinceCity())
                        && present(a.getWardCommune())).toList();
        if (validAddresses.stream().noneMatch(a -> a.getAddressType() == AddressType.CURRENT)) missing.add("currentAddress");
        if (validAddresses.stream().noneMatch(a -> a.getAddressType() == AddressType.PERMANENT
                || a.getAddressType() == AddressType.FAMILY_HOME)) missing.add("permanentOrFamilyAddress");
        var relatives = family.findByStudentId(studentId);
        for (var role : List.of(FamilyRelationship.FATHER, FamilyRelationship.MOTHER)) {
            if (relatives.stream().noneMatch(f -> f.getRelationship() == role
                    && (f.isUnavailable() || (present(f.getFullName()) && f.getDateOfBirth() != null))))
                missing.add(role == FamilyRelationship.FATHER ? "father" : "mother");
        }
        if (emergency.findByStudentId(studentId).stream().noneMatch(e -> present(e.getFullName())
                && present(e.getPhoneNumber()) && e.getPriority() > 0)) missing.add("emergencyContact");
        ProfileStatus status = missing.isEmpty() ? ProfileStatus.COMPLETE : ProfileStatus.INCOMPLETE;
        s.setProfileStatus(status);
        if (status == ProfileStatus.INCOMPLETE) s.setProfileCompletedAt(null);
        else if (s.getProfileCompletedAt() == null) s.setProfileCompletedAt(LocalDateTime.now());
        return new ProfileCompletionResult(status, missing);
    }

    // Call from future protected features; allow profile editing even when incomplete.
    @Transactional
    public void requireComplete(Long studentId) {
        if (refresh(studentId).status() != ProfileStatus.COMPLETE)
            throw new IllegalStateException("Complete the student profile before using this feature");
    }
    private static boolean present(String value) { return value != null && !value.isBlank(); }
    private static void need(List<String> missing, String field, Object value) {
        if (value == null || (value instanceof String s && s.isBlank())) missing.add(field);
    }
}
