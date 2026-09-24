package com.pbl4.studentweb.student.entity;

import jakarta.persistence.*;
import java.time.LocalDate;
import java.time.LocalDateTime;
import lombok.Getter;
import lombok.Setter;
import com.pbl4.studentweb.common.entity.*;
import com.pbl4.studentweb.user.entity.User;
import com.pbl4.studentweb.major.entity.Major;
import com.pbl4.studentweb.trainingprogram.entity.TrainingProgram;
import com.pbl4.studentweb.studentclass.entity.StudentClass;

@Getter
@Setter
@Entity
@Table(name = "students", indexes = {@Index(name = "idx_students_class_id", columnList = "class_id"), @Index(name = "idx_students_major_id", columnList = "major_id")})
public class Student extends AuditedEntity {
    @Column(name = "student_code", length = 20, nullable = false, unique = true)
    private String studentCode;

    @OneToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "user_id", nullable = false, unique = true)
    private User user;

    @Column(name = "full_name", length = 120, nullable = false)
    private String fullName;

    @Column(name = "avatar_url", length = 500)
    private String avatarUrl;

    @Column(name = "date_of_birth")
    private LocalDate dateOfBirth;

    @Enumerated(EnumType.STRING)
    @Column(name = "gender", length = 10)
    private Gender gender;

    @Column(name = "place_of_birth", length = 150)
    private String placeOfBirth;

    @Column(name = "old_place_of_birth", length = 150)
    private String oldPlaceOfBirth;

    @Column(name = "ethnicity", length = 50)
    private String ethnicity;

    @Column(name = "nationality", length = 50)
    private String nationality;

    @Column(name = "religion", length = 50)
    private String religion;

    @Column(name = "citizen_id", length = 20, unique = true)
    private String citizenId;

    @Column(name = "citizen_id_issue_date")
    private LocalDate citizenIdIssueDate;

    @Column(name = "health_insurance_number", length = 30)
    private String healthInsuranceNumber;

    @Column(name = "health_insurance_expiry")
    private LocalDate healthInsuranceExpiry;

    @org.hibernate.annotations.ColumnDefault("false")
    @Column(name = "free_health_insurance", nullable = false)
    private boolean freeHealthInsurance = false;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "major_id", nullable = false)
    private Major major;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "class_id", nullable = false)
    private StudentClass studentClass;

    @ManyToOne(fetch = FetchType.LAZY, optional = true)
    @JoinColumn(name = "training_program_id", nullable = true)
    private TrainingProgram trainingProgram;

    @ManyToOne(fetch = FetchType.LAZY, optional = true)
    @JoinColumn(name = "secondary_program_id", nullable = true)
    private TrainingProgram secondaryProgram;

    @Column(name = "school_email", length = 150, unique = true)
    private String schoolEmail;

    @Column(name = "personal_email", length = 150)
    private String personalEmail;

    @Column(name = "phone_number", length = 20)
    private String phoneNumber;

    @Column(name = "family_phone_number", length = 20)
    private String familyPhoneNumber;

    @Column(name = "facebook_url", length = 500)
    private String facebookUrl;

    @Column(name = "bank_account_number", length = 50)
    private String bankAccountNumber;

    @Column(name = "bank_name", length = 100)
    private String bankName;

    @Enumerated(EnumType.STRING)
    @org.hibernate.annotations.ColumnDefault("'INCOMPLETE'")
    @Column(name = "profile_status", length = 20, nullable = false)
    private ProfileStatus profileStatus = ProfileStatus.INCOMPLETE;

    @Column(name = "profile_completed_at")
    private LocalDateTime profileCompletedAt;

    @Enumerated(EnumType.STRING)
    @org.hibernate.annotations.ColumnDefault("'ACTIVE'")
    @Column(name = "status", length = 20, nullable = false)
    private StudentStatus status = StudentStatus.ACTIVE;
}
