package com.pbl4.studentweb.faculty.controller;

import com.pbl4.studentweb.faculty.dto.*;
import com.pbl4.studentweb.faculty.service.FacultyService;
import com.pbl4.studentweb.common.web.PageResponse;
import jakarta.validation.Valid;
import java.net.URI;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/faculties")
public class FacultyController {
    private final FacultyService service;

    @GetMapping
    public PageResponse<FacultySummary> list(@RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return PageResponse.from(service.findAll(PageResponse.request(page, size)));
    }
    @GetMapping("/{id}")
    public FacultySummary get(@PathVariable Long id) { return service.findById(id); }

    @PostMapping
    public ResponseEntity<FacultySummary> create(@Valid @RequestBody FacultyRequest request) {
        var result = service.create(request);
        return ResponseEntity.created(URI.create("/api/faculties/" + result.id())).body(result);
    }
    @PutMapping("/{id}")
    public FacultySummary update(@PathVariable Long id, @Valid @RequestBody FacultyRequest request) {
        return service.update(id, request);
    }
    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable Long id) {
        service.delete(id);
        return ResponseEntity.noContent().build();
    }
}
