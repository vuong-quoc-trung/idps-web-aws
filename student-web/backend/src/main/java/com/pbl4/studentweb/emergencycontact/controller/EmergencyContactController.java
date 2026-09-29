package com.pbl4.studentweb.emergencycontact.controller;

import com.pbl4.studentweb.emergencycontact.dto.*;
import com.pbl4.studentweb.emergencycontact.service.EmergencyContactService;
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
@RequestMapping({"/api/students/{studentId}/emergency-contacts", "/api/me/emergency-contacts"})
public class EmergencyContactController {
    private final EmergencyContactService service;
    private final CurrentAccount account;

    @GetMapping
    public List<EmergencyContactSummary> list(Authentication auth, @PathVariable(required = false) Long studentId) {
        return service.findByStudentId(account.studentId(auth, studentId));
    }
    @GetMapping("/{id}")
    public EmergencyContactSummary get(Authentication auth, @PathVariable(required = false) Long studentId, @PathVariable Long id) {
        return service.findById(account.studentId(auth, studentId), id);
    }
    @PostMapping
    public ResponseEntity<EmergencyContactSummary> create(Authentication auth, @PathVariable(required = false) Long studentId,
            @Valid @RequestBody EmergencyContactRequest request) {
        var result = service.create(account.studentId(auth, studentId), request);
        String base = studentId == null ? "/api/me" : "/api/students/" + studentId;
        return ResponseEntity.created(URI.create(base + "/emergency-contacts/" + result.id())).body(result);
    }
    @PutMapping("/{id}")
    public EmergencyContactSummary update(Authentication auth, @PathVariable(required = false) Long studentId,
            @PathVariable Long id, @Valid @RequestBody EmergencyContactRequest request) {
        return service.update(account.studentId(auth, studentId), id, request);
    }
    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(Authentication auth, @PathVariable(required = false) Long studentId,
            @PathVariable Long id) {
        service.delete(account.studentId(auth, studentId), id);
        return ResponseEntity.noContent().build();
    }
}
