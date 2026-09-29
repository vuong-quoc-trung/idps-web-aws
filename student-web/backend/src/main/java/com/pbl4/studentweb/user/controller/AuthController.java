package com.pbl4.studentweb.user.controller;

import com.pbl4.studentweb.user.dto.UserSummary;
import com.pbl4.studentweb.user.service.*;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.*;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/auth")
public class AuthController {
    private final PasswordSetupService passwords;
    private final UserAccountService users;
    private final CurrentAccount account;
    public record CsrfResponse(String headerName, String token) {}
    public record ActivationRequest(@NotBlank @Size(max = 200) String token,
                                    @NotBlank @Size(min = 12, max = 72) String password) {
        @Override public String toString() { return "ActivationRequest[redacted]"; }
    }
    @GetMapping("/csrf")
    public CsrfResponse csrf(CsrfToken token) { return new CsrfResponse(token.getHeaderName(), token.getToken()); }

    @GetMapping("/me")
    public UserSummary me(Authentication auth) { return users.findById(account.userId(auth)); }

    @PostMapping("/activate")
    public ResponseEntity<Void> activate(@Valid @RequestBody ActivationRequest request) {
        passwords.setInitialPassword(request.token(), request.password());
        return ResponseEntity.noContent().build();
    }
}
