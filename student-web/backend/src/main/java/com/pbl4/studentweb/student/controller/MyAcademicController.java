package com.pbl4.studentweb.student.controller;

import com.pbl4.studentweb.student.repository.StudentRepository;
import com.pbl4.studentweb.user.service.CurrentAccount;
import com.pbl4.studentweb.common.web.PageResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.Authentication;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/me/academic")
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class MyAcademicController {
    private final StudentRepository students;
    private final CurrentAccount account;
    public record Item(String code, String name) {}
    public record Academic(Item faculty, Item major, Item program, Item secondaryProgram, Item studentClass, Integer cohort) {}
    public record Classmate(String studentCode, String fullName, boolean self) {}

    @GetMapping
    public Academic academic(Authentication auth) {
        var student = students.findById(account.studentId(auth, null)).orElseThrow();
        var major = student.getMajor();
        var faculty = major.getFaculty();
        var program = student.getTrainingProgram();
        var secondary = student.getSecondaryProgram();
        var group = student.getStudentClass();
        return new Academic(new Item(faculty.getFacultyCode(), faculty.getFacultyName()),
            new Item(major.getMajorCode(), major.getMajorName()),
            new Item(program.getProgramCode(), program.getProgramName()),
            secondary == null ? null : new Item(secondary.getProgramCode(), secondary.getProgramName()),
            new Item(group.getClassCode(), group.getClassName()), group.getCohort());
    }

    @GetMapping("/classmates")
    public PageResponse<Classmate> classmates(Authentication auth,
            @RequestParam(defaultValue = "") String search,
            @RequestParam(defaultValue = "0") int page, @RequestParam(defaultValue = "20") int size) {
        var student = students.findById(account.studentId(auth, null)).orElseThrow();
        // Class scope comes only from the authenticated student's record, never request IDs.
        if (search.length() > 120) throw new IllegalArgumentException("Search is too long");
        String pattern = "%" + search.trim().toLowerCase(java.util.Locale.ROOT).replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%";
        org.springframework.data.jpa.domain.Specification<com.pbl4.studentweb.student.entity.Student> filter = (root, query, cb) ->
            cb.and(cb.equal(root.get("studentClass").get("id"), student.getStudentClass().getId()),
                cb.or(cb.like(cb.lower(root.get("fullName")), pattern, '!'), cb.like(cb.lower(root.get("studentCode")), pattern, '!')));
        return PageResponse.from(students.findAll(filter,
            PageResponse.request(page, size)).map(member -> new Classmate(member.getStudentCode(),
                member.getFullName(), member.getId().equals(student.getId()))));
    }
}
