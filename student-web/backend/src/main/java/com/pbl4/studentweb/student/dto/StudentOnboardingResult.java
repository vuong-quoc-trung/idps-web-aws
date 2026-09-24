package com.pbl4.studentweb.student.dto;

/** Contains a one-time secret: do not log or include in a general student response. */
public final class StudentOnboardingResult {
    private final StudentSummary student;
    private final String activationToken;
    public StudentOnboardingResult(StudentSummary student, String activationToken) {
        this.student = student;
        this.activationToken = activationToken;
    }
    public StudentSummary student() { return student; }
    public String activationToken() { return activationToken; }
    @Override public String toString() { return "StudentOnboardingResult[redacted]"; }
}
