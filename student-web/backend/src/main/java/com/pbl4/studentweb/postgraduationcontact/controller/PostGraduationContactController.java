package com.pbl4.studentweb.postgraduationcontact.controller;

import com.pbl4.studentweb.postgraduationcontact.dto.*;
import com.pbl4.studentweb.postgraduationcontact.service.PostGraduationContactService;
import com.pbl4.studentweb.user.service.CurrentAccount;
import jakarta.validation.Valid;
import java.net.URI;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

@RestController
@RequiredArgsConstructor
@RequestMapping({"/api/students/{studentId}/post-graduation-contacts", "/api/me/post-graduation-contacts"})
public class PostGraduationContactController {
    private final PostGraduationContactService service;
    private final CurrentAccount account;

    @GetMapping
    public List<PostGraduationContactSummary> list(Authentication auth, @PathVariable(required = false) Long studentId) {
        return service.findByStudentId(account.studentId(auth, studentId));
    }
    @GetMapping("/{id}")
    public PostGraduationContactSummary get(Authentication auth, @PathVariable(required = false) Long studentId, @PathVariable Long id) {
        return service.findById(account.studentId(auth, studentId), id);
    }
    @PostMapping
    public ResponseEntity<PostGraduationContactSummary> create(Authentication auth, @PathVariable(required = false) Long studentId,
            @Valid @RequestBody PostGraduationContactRequest request) {
        var result = service.create(account.studentId(auth, studentId), request);
        String base = studentId == null ? "/api/me" : "/api/students/" + studentId;
        return ResponseEntity.created(URI.create(base + "/post-graduation-contacts/" + result.id())).body(result);
    }
    @PutMapping("/{id}")
    public PostGraduationContactSummary update(Authentication auth, @PathVariable(required = false) Long studentId,
            @PathVariable Long id, @Valid @RequestBody PostGraduationContactRequest request) {
        return service.update(account.studentId(auth, studentId), id, request);
    }
    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(Authentication auth, @PathVariable(required = false) Long studentId,
            @PathVariable Long id) {
        service.delete(account.studentId(auth, studentId), id);
        return ResponseEntity.noContent().build();
    }
}
