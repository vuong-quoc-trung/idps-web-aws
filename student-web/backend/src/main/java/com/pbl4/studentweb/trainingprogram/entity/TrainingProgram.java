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
@org.hibernate.annotations.Check(name = "ck_training_program_academic_numbers", constraints = """
            (number_of_semesters IS NULL OR number_of_semesters > 0)
            AND (total_credits IS NULL OR total_credits >= 0)
            AND (required_credits IS NULL OR required_credits >= 0)
            AND (elective_credits IS NULL OR elective_credits >= 0)
            AND (total_credits IS NULL OR required_credits IS NULL OR required_credits <= total_credits)
            AND (total_credits IS NULL OR elective_credits IS NULL OR elective_credits <= total_credits)
            AND (total_credits IS NULL OR required_credits IS NULL OR elective_credits IS NULL
                 OR CAST(required_credits AS BIGINT) + CAST(elective_credits AS BIGINT) = total_credits)
            """)
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

    @Enumerated(EnumType.STRING)
    @Column(name = "degree_type", length = 50)
    private DegreeType degreeType;

    @Column(name = "number_of_semesters")
    private Integer numberOfSemesters;

    @Column(name = "total_credits")
    private Integer totalCredits;

    @Column(name = "required_credits")
    private Integer requiredCredits;

    @Column(name = "elective_credits")
    private Integer electiveCredits;

    @org.hibernate.annotations.ColumnDefault("true")
    @Column(name = "active", nullable = false)
    private boolean active = true;
}
