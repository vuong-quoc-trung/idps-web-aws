package com.pbl4.studentweb.studentclass.controller;

import com.pbl4.studentweb.studentclass.dto.*;
import com.pbl4.studentweb.studentclass.service.StudentClassService;
import com.pbl4.studentweb.common.web.PageResponse;
import jakarta.validation.Valid;
import java.net.URI;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/classes")
public class StudentClassController {
    private final StudentClassService service;

    @GetMapping
    public PageResponse<StudentClassSummary> list(@RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return PageResponse.from(service.findAll(PageResponse.request(page, size)));
    }
    @GetMapping("/{id}")
    public StudentClassSummary get(@PathVariable Long id) { return service.findById(id); }

    @PostMapping
    public ResponseEntity<StudentClassSummary> create(@Valid @RequestBody StudentClassRequest request) {
        var result = service.create(request);
        return ResponseEntity.created(URI.create("/api/classes/" + result.id())).body(result);
    }
    @PutMapping("/{id}")
    public StudentClassSummary update(@PathVariable Long id, @Valid @RequestBody StudentClassRequest request) {
        return service.update(id, request);
    }
    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable Long id) {
        service.delete(id);
        return ResponseEntity.noContent().build();
    }
}
