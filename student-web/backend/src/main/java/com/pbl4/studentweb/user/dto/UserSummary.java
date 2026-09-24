package com.pbl4.studentweb.user.dto;

import com.pbl4.studentweb.user.entity.UserRole;
public record UserSummary(Long id, String username, UserRole role, boolean enabled,
                          boolean passwordSetupRequired) {}
