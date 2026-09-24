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
@Table(name = "majors")
public class Major extends BaseEntity {
    @Column(name = "major_code", length = 20, nullable = false, unique = true)
    private String majorCode;

    @Column(name = "major_name", length = 150, nullable = false)
    private String majorName;

    @Column(name = "description", columnDefinition = "text")
    private String description;

    @org.hibernate.annotations.ColumnDefault("true")
    @Column(name = "active", nullable = false)
    private boolean active = true;
}
