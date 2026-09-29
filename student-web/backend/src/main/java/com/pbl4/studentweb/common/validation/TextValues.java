package com.pbl4.studentweb.common.validation;

public final class TextValues {
    private TextValues() {}
    public static String optional(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }
}
