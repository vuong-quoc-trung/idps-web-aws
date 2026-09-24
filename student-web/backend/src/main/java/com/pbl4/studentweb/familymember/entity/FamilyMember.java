package com.pbl4.studentweb.familymember.entity;

import jakarta.persistence.*;
import java.time.LocalDate;
import java.time.LocalDateTime;
import lombok.Getter;
import lombok.Setter;
import com.pbl4.studentweb.common.entity.*;
import com.pbl4.studentweb.student.entity.Student;

@Getter
@Setter
@Entity
@Table(name = "family_members", indexes = {@Index(name = "idx_family_members_student_id", columnList = "student_id")})
public class FamilyMember extends AuditedEntity {
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "student_id", nullable = false)
    private Student student;

    @Enumerated(EnumType.STRING)
    @Column(name = "relationship", length = 20, nullable = false)
    private FamilyRelationship relationship;

    @Column(name = "full_name", length = 120)
    private String fullName;

    @Column(name = "date_of_birth")
    private LocalDate dateOfBirth;

    @org.hibernate.annotations.ColumnDefault("false")
    @Column(name = "has_college_degree", nullable = false)
    private boolean hasCollegeDegree = false;

    @org.hibernate.annotations.ColumnDefault("false")
    @Column(name = "unavailable", nullable = false)
    private boolean unavailable = false;

    @Column(name = "phone_number", length = 20)
    private String phoneNumber;
}
