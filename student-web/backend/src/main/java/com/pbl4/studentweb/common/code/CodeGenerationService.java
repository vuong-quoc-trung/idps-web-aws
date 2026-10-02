package com.pbl4.studentweb.common.code;

import com.pbl4.studentweb.major.entity.Major;
import com.pbl4.studentweb.trainingprogram.entity.DegreeType;
import com.pbl4.studentweb.student.repository.StudentRepository;
import com.pbl4.studentweb.studentclass.repository.StudentClassRepository;
import com.pbl4.studentweb.user.repository.UserRepository;
import java.util.Locale;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class CodeGenerationService {
    private final CodeCounterAllocator counters;
    private final StudentRepository students;
    private final StudentClassRepository classes;
    private final UserRepository users;

    public String normalizeShortCode(String value) {
        String normalized = value == null ? "" : value.trim().toUpperCase(Locale.ROOT);
        if (!normalized.matches("[A-Z][A-Z0-9]{0,9}"))
            throw new IllegalArgumentException("shortCode must contain 1-10 ASCII letters/digits, starting with a letter");
        return normalized;
    }
    public int cohort(Integer value) {
        if (value == null || value < 1000 || value > 9999)
            throw new IllegalArgumentException("Cohort must be a four-digit year");
        return value;
    }
    public String faculty(String shortCode) { return "FAC-" + normalizeShortCode(shortCode); }
    public String major(String shortCode) { return "MAJ-" + normalizeShortCode(shortCode); }
    public String program(Major major, Integer year, DegreeType degree) {
        if (degree == null) throw new IllegalArgumentException("Degree type is required");
        String suffix = switch (degree) {
            case ENGINEER -> "ENG";
            case BACHELOR -> "BSC";
            case MASTER -> "MSC";
        };
        return "PRG-" + normalizeShortCode(major.getShortCode()) + "-" + cohort(year) + "-" + suffix;
    }
    public String studentClass(Major major, Integer year) {
        String prefix = "CLS-" + normalizeShortCode(major.getShortCode()) + "-" + cohort(year) + "-";
        String code;
        do {
            code = prefix + String.format(Locale.ROOT, "%02d", counters.next(prefix, Long.MAX_VALUE));
        } while (classes.existsByClassCode(code));
        return code;
    }
    public String student(Integer year) {
        String prefix = "STU-" + cohort(year) + "-";
        String code;
        do {
            code = prefix + String.format(Locale.ROOT, "%06d", counters.next(prefix, 999999));
        } while (students.existsByStudentCode(code) || users.existsByUsername(code));
        return code;
    }
}
