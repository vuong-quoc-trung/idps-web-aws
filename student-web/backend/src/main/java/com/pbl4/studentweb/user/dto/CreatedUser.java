package com.pbl4.studentweb.user.dto;

public record CreatedUser(UserSummary user, String activationToken) {
    @Override public String toString() { return "CreatedUser[redacted]"; }
}
