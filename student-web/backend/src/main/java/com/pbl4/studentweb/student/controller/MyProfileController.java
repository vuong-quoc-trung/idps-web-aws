package com.pbl4.studentweb.student.controller;

import com.pbl4.studentweb.student.dto.*;
import com.pbl4.studentweb.student.service.*;
import com.pbl4.studentweb.user.service.CurrentAccount;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/me")
public class MyProfileController {
    private final CurrentAccount account;
    private final StudentService students;
    private final StudentProfileService profiles;
    private final StudentProfileCompletionService completion;

    @GetMapping("/profile")
    public StudentDetail get(Authentication auth) { return students.findById(account.studentId(auth, null)); }

    @PutMapping("/profile")
    public ProfileCompletionResult update(Authentication auth, @Valid @RequestBody UpdateStudentProfileRequest request) {
        return profiles.updateForUser(account.userId(auth), request);
    }
    @GetMapping("/completion")
    public ProfileCompletionResult completion(Authentication auth) { return completion.check(account.studentId(auth, null)); }
}
