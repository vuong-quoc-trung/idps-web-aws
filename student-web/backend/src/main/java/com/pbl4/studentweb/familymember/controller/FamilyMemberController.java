package com.pbl4.studentweb.familymember.controller;

import com.pbl4.studentweb.familymember.dto.*;
import com.pbl4.studentweb.familymember.service.FamilyMemberService;
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
@RequestMapping({"/api/students/{studentId}/family-members", "/api/me/family-members"})
public class FamilyMemberController {
    private final FamilyMemberService service;
    private final CurrentAccount account;

    @GetMapping
    public List<FamilyMemberSummary> list(Authentication auth, @PathVariable(required = false) Long studentId) {
        return service.findByStudentId(account.studentId(auth, studentId));
    }
    @GetMapping("/{id}")
    public FamilyMemberSummary get(Authentication auth, @PathVariable(required = false) Long studentId, @PathVariable Long id) {
        return service.findById(account.studentId(auth, studentId), id);
    }
    @PostMapping
    public ResponseEntity<FamilyMemberSummary> create(Authentication auth, @PathVariable(required = false) Long studentId,
            @Valid @RequestBody FamilyMemberRequest request) {
        var result = service.create(account.studentId(auth, studentId), request);
        String base = studentId == null ? "/api/me" : "/api/students/" + studentId;
        return ResponseEntity.created(URI.create(base + "/family-members/" + result.id())).body(result);
    }
    @PutMapping("/{id}")
    public FamilyMemberSummary update(Authentication auth, @PathVariable(required = false) Long studentId,
            @PathVariable Long id, @Valid @RequestBody FamilyMemberRequest request) {
        return service.update(account.studentId(auth, studentId), id, request);
    }
    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(Authentication auth, @PathVariable(required = false) Long studentId,
            @PathVariable Long id) {
        service.delete(account.studentId(auth, studentId), id);
        return ResponseEntity.noContent().build();
    }
}
