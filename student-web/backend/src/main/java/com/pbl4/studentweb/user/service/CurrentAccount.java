package com.pbl4.studentweb.user.service;

import com.pbl4.studentweb.common.exception.ResourceNotFoundException;
import com.pbl4.studentweb.student.repository.StudentRepository;
import com.pbl4.studentweb.user.entity.User;
import com.pbl4.studentweb.user.repository.UserRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class CurrentAccount {
    private final UserRepository users;
    private final StudentRepository students;

    public Long userId(Authentication auth) { return require(auth).getId(); }

    public Long studentId(Authentication auth, Long requestedStudentId) {
        var user = require(auth);
        if (requestedStudentId != null) {
            if (user.getRole() != com.pbl4.studentweb.user.entity.UserRole.ADMIN
                    && user.getRole() != com.pbl4.studentweb.user.entity.UserRole.STAFF)
                throw new AccessDeniedException("Not allowed");
            return requestedStudentId;
        }
        return students.findByUserId(user.getId()).orElseThrow(() -> new ResourceNotFoundException("Student")).getId();
    }
    private User require(Authentication auth) {
        if (auth == null || !auth.isAuthenticated()) throw new AccessDeniedException("Not authenticated");
        var user = users.findByUsername(auth.getName()).orElseThrow(() -> new AccessDeniedException("Not authenticated"));
        if (!user.isEnabled() || user.isPasswordSetupRequired()) throw new AccessDeniedException("Account is not active");
        return user;
    }
}
