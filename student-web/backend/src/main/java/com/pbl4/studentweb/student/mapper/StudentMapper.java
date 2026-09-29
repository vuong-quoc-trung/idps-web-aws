package com.pbl4.studentweb.student.mapper;

import com.pbl4.studentweb.student.entity.Student;
import com.pbl4.studentweb.student.dto.StudentSummary;
import org.springframework.stereotype.Component;
@Component
public class StudentMapper {
    public StudentSummary toSummary(Student s) {
        return new StudentSummary(s.getId(), s.getStudentCode(), s.getFullName(),
                s.getMajor().getId(), s.getStudentClass().getId(), s.getProfileStatus(), s.getStatus());
    }

    public com.pbl4.studentweb.student.dto.StudentDetail toDetail(Student s) {
        return new com.pbl4.studentweb.student.dto.StudentDetail(
                s.getId(), s.getUser().getId(), s.getStudentCode(), s.getFullName(), s.getAvatarUrl(),
                s.getDateOfBirth(), s.getGender(), s.getPlaceOfBirth(), s.getOldPlaceOfBirth(),
                s.getEthnicity(), s.getNationality(), s.getReligion(), s.getCitizenId(), s.getCitizenIdIssueDate(),
                s.getHealthInsuranceNumber(), s.getHealthInsuranceExpiry(), s.isFreeHealthInsurance(),
                s.getMajor().getId(), s.getStudentClass().getId(),
                s.getTrainingProgram() == null ? null : s.getTrainingProgram().getId(),
                s.getSecondaryProgram() == null ? null : s.getSecondaryProgram().getId(),
                s.getSchoolEmail(), s.getPersonalEmail(), s.getPhoneNumber(), s.getFamilyPhoneNumber(),
                s.getFacebookUrl(), s.getBankAccountNumber(), s.getBankName(),
                s.getProfileStatus(), s.getProfileCompletedAt(), s.getStatus());
    }
}
