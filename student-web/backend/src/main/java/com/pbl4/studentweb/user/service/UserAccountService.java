package com.pbl4.studentweb.user.service;

import com.pbl4.studentweb.common.exception.ResourceNotFoundException;
import com.pbl4.studentweb.student.entity.StudentStatus;
import com.pbl4.studentweb.student.repository.StudentRepository;
import com.pbl4.studentweb.user.dto.*;
import com.pbl4.studentweb.user.entity.*;
import com.pbl4.studentweb.user.mapper.UserMapper;
import com.pbl4.studentweb.user.repository.UserRepository;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import java.time.LocalDateTime;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class UserAccountService {
    private final UserRepository users;
    private final StudentRepository students;
    private final UserMapper mapper;
    private final PasswordSetupService passwords;

    public Page<UserSummary> findAll(Pageable page) { return users.findAll(page).map(mapper::toSummary); }
    public UserSummary findById(Long id) { return mapper.toSummary(require(id)); }

    @Transactional
    public CreatedUser create(@NotNull @Valid CreateUserRequest request) {
        if (request.role() == UserRole.STUDENT) throw new IllegalArgumentException("Create student accounts through student onboarding");
        String username = request.username().trim();
        if (users.existsByUsername(username)) throw new IllegalStateException("Username already exists");
        var user = new User();
        user.setUsername(username);
        user.setRole(request.role());
        String token = passwords.prepareNewAccount(user);
        return new CreatedUser(mapper.toSummary(users.saveAndFlush(user)), token);
    }
    @Transactional
    public UserSummary setEnabled(Long id, boolean enabled, Long actorId) {
        var user = require(id);
        if (!enabled && id.equals(actorId)) throw new IllegalStateException("Cannot disable your own account");
        if (enabled) students.findByUserId(id).ifPresent(student -> {
            if (student.getStatus() == StudentStatus.INACTIVE || student.getStatus() == StudentStatus.SUSPENDED)
                throw new IllegalStateException("Restore the student status before enabling the account");
        });
        user.setEnabled(enabled);
        return mapper.toSummary(user);
    }
    @Transactional
    public CreatedUser reissueActivation(Long id) {
        String token = passwords.reissueActivation(id);
        return new CreatedUser(mapper.toSummary(require(id)), token);
    }

    @Transactional
    public void recordLogin(String username) {
        users.findByUsername(username).ifPresent(user -> user.setLastLoginAt(LocalDateTime.now()));
    }
    private User require(Long id) {
        return users.findById(id).orElseThrow(() -> new ResourceNotFoundException("User"));
    }
}
