package com.pbl4.studentweb.user.dto;

import com.pbl4.studentweb.user.entity.UserRole;
import jakarta.validation.constraints.*;

public record CreateUserRequest(@NotBlank @Size(max = 50) String username, @NotNull UserRole role) {}
