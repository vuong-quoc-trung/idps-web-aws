package com.pbl4.studentweb.faculty.entity;

import com.pbl4.studentweb.common.entity.BaseEntity;
import jakarta.persistence.*;
import lombok.Getter;
import lombok.Setter;

@Getter
@Setter
@Entity
@Table(name = "faculties")
public class Faculty extends BaseEntity {
    @Column(name = "short_code", length = 10, unique = true)
    private String shortCode;

    @Column(name = "faculty_code", length = 20, nullable = false, unique = true)
    private String facultyCode;
    @Column(name = "faculty_name", length = 150, nullable = false)
    private String facultyName;
    @Column(name = "description", columnDefinition = "text")
    private String description;
    @Column(name = "active", nullable = false)
    private boolean active = true;
}
