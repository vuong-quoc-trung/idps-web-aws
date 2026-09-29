package com.pbl4.studentweb.trainingprogram.controller;

import com.pbl4.studentweb.trainingprogram.dto.*;
import com.pbl4.studentweb.trainingprogram.service.TrainingProgramService;
import com.pbl4.studentweb.common.web.PageResponse;
import jakarta.validation.Valid;
import java.net.URI;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/training-programs")
public class TrainingProgramController {
    private final TrainingProgramService service;

    @GetMapping
    public PageResponse<TrainingProgramSummary> list(@RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return PageResponse.from(service.findAll(PageResponse.request(page, size)));
    }
    @GetMapping("/{id}")
    public TrainingProgramSummary get(@PathVariable Long id) { return service.findById(id); }

    @PostMapping
    public ResponseEntity<TrainingProgramSummary> create(@Valid @RequestBody TrainingProgramRequest request) {
        var result = service.create(request);
        return ResponseEntity.created(URI.create("/api/training-programs/" + result.id())).body(result);
    }
    @PutMapping("/{id}")
    public TrainingProgramSummary update(@PathVariable Long id, @Valid @RequestBody TrainingProgramRequest request) {
        return service.update(id, request);
    }
    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable Long id) {
        service.delete(id);
        return ResponseEntity.noContent().build();
    }
}
