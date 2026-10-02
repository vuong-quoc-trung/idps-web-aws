package com.pbl4.studentweb.major.dto;

public record MajorSummary(Long id, String code, String shortCode, String name, String description, Long facultyId, boolean active) {}
