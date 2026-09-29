package com.pbl4.studentweb.user.controller;

import com.pbl4.studentweb.common.web.PageResponse;
import com.pbl4.studentweb.user.dto.*;
import com.pbl4.studentweb.user.service.*;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import java.net.URI;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/users")
public class UserController {
    private final UserAccountService users;
    private final CurrentAccount account;
    public record EnabledRequest(@NotNull Boolean enabled) {}

    @GetMapping
    public PageResponse<UserSummary> list(@RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return PageResponse.from(users.findAll(PageResponse.request(page, size)));
    }
    @GetMapping("/{id}")
    public UserSummary get(@PathVariable Long id) { return users.findById(id); }

    @PostMapping
    public ResponseEntity<CreatedUser> create(@Valid @RequestBody CreateUserRequest request) {
        var result = users.create(request);
        return ResponseEntity.created(URI.create("/api/users/" + result.user().id())).body(result);
    }
    @PatchMapping("/{id}/enabled")
    public UserSummary enabled(Authentication auth, @PathVariable Long id, @Valid @RequestBody EnabledRequest request) {
        return users.setEnabled(id, request.enabled(), account.userId(auth));
    }

    @PostMapping("/{id}/activation-token")
    public CreatedUser reissueActivation(@PathVariable Long id) { return users.reissueActivation(id); }
}
