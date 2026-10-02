package com.pbl4.studentweb.major.entity;

import jakarta.persistence.*;
import java.time.LocalDate;
import java.time.LocalDateTime;
import lombok.Getter;
import lombok.Setter;
import com.pbl4.studentweb.common.entity.*;

@Getter
@Setter
@Entity
@Table(name = "majors", indexes = @Index(name = "idx_majors_faculty_id", columnList = "faculty_id"))
public class Major extends BaseEntity {
    @Column(name = "short_code", length = 10, unique = true)
    private String shortCode;

    @Column(name = "major_code", length = 20, nullable = false, unique = true)
    private String majorCode;

    @Column(name = "major_name", length = 150, nullable = false)
    private String majorName;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "faculty_id", nullable = false, foreignKey = @ForeignKey(name = "fk_majors_faculty"))
    private com.pbl4.studentweb.faculty.entity.Faculty faculty;

    @Column(name = "description", columnDefinition = "text")
    private String description;

    @org.hibernate.annotations.ColumnDefault("true")
    @Column(name = "active", nullable = false)
    private boolean active = true;
}
