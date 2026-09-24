package com.pbl4.studentweb.postgraduationcontact.entity;

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
@Table(name = "post_graduation_contacts", indexes = {@Index(name = "idx_post_graduation_contacts_student_id", columnList = "student_id")})
public class PostGraduationContact extends AuditedEntity {
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "student_id", nullable = false)
    private Student student;

    @Column(name = "full_name", length = 120)
    private String fullName;

    @Column(name = "phone_number", length = 20)
    private String phoneNumber;

    @Column(name = "email", length = 150)
    private String email;

    @Column(name = "address", length = 255)
    private String address;
}
