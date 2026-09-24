package com.pbl4.studentweb.emergencycontact.entity;

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
@Table(name = "emergency_contacts", indexes = {@Index(name = "idx_emergency_contacts_student_id", columnList = "student_id")})
public class EmergencyContact extends AuditedEntity {
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "student_id", nullable = false)
    private Student student;

    @Column(name = "full_name", length = 120, nullable = false)
    private String fullName;

    @Column(name = "relationship", length = 50)
    private String relationship;

    @Column(name = "phone_number", length = 20, nullable = false)
    private String phoneNumber;

    @Column(name = "address", length = 255)
    private String address;

    @org.hibernate.annotations.ColumnDefault("1")
    @Column(name = "priority", nullable = false)
    private int priority = 1;
}
