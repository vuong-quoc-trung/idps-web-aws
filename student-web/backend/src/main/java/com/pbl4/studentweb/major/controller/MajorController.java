package com.pbl4.studentweb.major.controller;

import com.pbl4.studentweb.major.dto.*;
import com.pbl4.studentweb.major.service.MajorService;
import com.pbl4.studentweb.common.web.PageResponse;
import jakarta.validation.Valid;
import java.net.URI;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/majors")
public class MajorController {
    private final MajorService service;

    @GetMapping
    public PageResponse<MajorSummary> list(@RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return PageResponse.from(service.findAll(PageResponse.request(page, size)));
    }
    @GetMapping("/{id}")
    public MajorSummary get(@PathVariable Long id) { return service.findById(id); }

    @PostMapping
    public ResponseEntity<MajorSummary> create(@Valid @RequestBody MajorRequest request) {
        var result = service.create(request);
        return ResponseEntity.created(URI.create("/api/majors/" + result.id())).body(result);
    }
    @PutMapping("/{id}")
    public MajorSummary update(@PathVariable Long id, @Valid @RequestBody MajorRequest request) {
        return service.update(id, request);
    }
    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable Long id) {
        service.delete(id);
        return ResponseEntity.noContent().build();
    }
}
