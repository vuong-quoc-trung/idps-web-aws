package com.pbl4.studentweb.student.controller;

import com.pbl4.studentweb.common.web.PageResponse;
import com.pbl4.studentweb.student.dto.*;
import com.pbl4.studentweb.student.entity.StudentStatus;
import com.pbl4.studentweb.student.service.*;
import jakarta.validation.Valid;
import java.net.URI;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/students")
public class StudentController {
    private final StudentService service;
    private final StudentOnboardingService onboarding;
    private final StudentProfileCompletionService completion;

    public record CreatedStudent(StudentSummary student, String activationToken) {
        @Override public String toString() { return "CreatedStudent[redacted]"; }
    }
    @GetMapping
    public PageResponse<StudentSummary> list(@RequestParam(required = false) String search,
            @RequestParam(required = false) Long majorId, @RequestParam(required = false) Long classId,
            @RequestParam(required = false) StudentStatus status,
            @RequestParam(defaultValue = "0") int page, @RequestParam(defaultValue = "20") int size) {
        return PageResponse.from(service.findAll(search, majorId, classId, status, PageResponse.request(page, size)));
    }
    @GetMapping("/{id}")
    public StudentDetail get(@PathVariable Long id) { return service.findById(id); }

    @PostMapping
    public ResponseEntity<CreatedStudent> create(@Valid @RequestBody CreateStudentRequest request) {
        var result = onboarding.create(request);
        return ResponseEntity.created(URI.create("/api/students/" + result.student().id()))
                .body(new CreatedStudent(result.student(), result.activationToken()));
    }
    @PutMapping("/{id}")
    public StudentDetail update(@PathVariable Long id, @Valid @RequestBody UpdateStudentRequest request) {
        return service.update(id, request);
    }
    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable Long id) {
        service.delete(id);
        return ResponseEntity.noContent().build();
    }
    @GetMapping("/{id}/completion")
    public ProfileCompletionResult completion(@PathVariable Long id) { return completion.check(id); }
}
