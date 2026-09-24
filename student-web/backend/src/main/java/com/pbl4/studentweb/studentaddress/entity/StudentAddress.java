package com.pbl4.studentweb.studentaddress.entity;

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
@Table(name = "student_addresses", indexes = {@Index(name = "idx_student_addresses_student_id", columnList = "student_id")})
public class StudentAddress extends AuditedEntity {
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "student_id", nullable = false)
    private Student student;

    @Enumerated(EnumType.STRING)
    @Column(name = "address_type", length = 30, nullable = false)
    private AddressType addressType;

    @Column(name = "address_line", length = 255)
    private String addressLine;

    @Column(name = "province_city", length = 100)
    private String provinceCity;

    @Column(name = "ward_commune", length = 100)
    private String wardCommune;

    @Column(name = "residence_relation", length = 50)
    private String residenceRelation;

    @org.hibernate.annotations.ColumnDefault("true")
    @Column(name = "is_current", nullable = false)
    private boolean isCurrent = true;
}
