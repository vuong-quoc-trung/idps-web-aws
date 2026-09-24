package com.pbl4.studentweb.trainingprogram.entity;

import jakarta.persistence.*;
import java.time.LocalDate;
import java.time.LocalDateTime;
import lombok.Getter;
import lombok.Setter;
import com.pbl4.studentweb.common.entity.*;
import com.pbl4.studentweb.major.entity.Major;

@Getter
@Setter
@Entity
@Table(name = "training_programs")
public class TrainingProgram extends BaseEntity {
    @Column(name = "program_code", length = 30, nullable = false, unique = true)
    private String programCode;

    @Column(name = "program_name", length = 200, nullable = false)
    private String programName;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "major_id", nullable = false)
    private Major major;

    @Column(name = "cohort")
    private Integer cohort;

    @Column(name = "degree_type", length = 50)
    private String degreeType;

    @org.hibernate.annotations.ColumnDefault("true")
    @Column(name = "active", nullable = false)
    private boolean active = true;
}
