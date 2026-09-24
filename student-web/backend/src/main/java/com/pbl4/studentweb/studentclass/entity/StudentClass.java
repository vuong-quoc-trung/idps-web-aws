package com.pbl4.studentweb.studentclass.entity;

import jakarta.persistence.*;
import java.time.LocalDate;
import java.time.LocalDateTime;
import lombok.Getter;
import lombok.Setter;
import com.pbl4.studentweb.common.entity.*;
import com.pbl4.studentweb.major.entity.Major;
import com.pbl4.studentweb.trainingprogram.entity.TrainingProgram;

@Getter
@Setter
@Entity
@Table(name = "classes")
public class StudentClass extends BaseEntity {
    @Column(name = "class_code", length = 30, nullable = false, unique = true)
    private String classCode;

    @Column(name = "class_name", length = 100)
    private String className;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "major_id", nullable = false)
    private Major major;

    @ManyToOne(fetch = FetchType.LAZY, optional = true)
    @JoinColumn(name = "program_id", nullable = true)
    private TrainingProgram program;

    @Column(name = "cohort")
    private Integer cohort;

    @Column(name = "academic_year", length = 20)
    private String academicYear;

    @org.hibernate.annotations.ColumnDefault("true")
    @Column(name = "active", nullable = false)
    private boolean active = true;
}
