package com.pbl4.studentweb.common.validation;

public final class ContactValues {
    private ContactValues() {}
    public static String phone(String raw) {
        String value = TextValues.optional(raw);
        return value == null ? null : value.replaceAll("[ .()\\-]", "");
    }
    public static boolean validPhone(String raw) {
        if (raw == null || raw.isBlank()) return true;
        if (raw.length() > 40 || !raw.matches("[+0-9 .()\\-]+")) return false;
        String value = phone(raw);
        if (value.matches("(?:0|\\+84)(?:[35789][0-9]{8}|2[0-9]{9})")) return true;
        return !value.startsWith("+84") && value.matches("\\+[1-9][0-9]{7,14}");
    }
    public static boolean validEmail(String raw) {
        if (raw == null || raw.isBlank()) return true;
        String value = raw.trim();
        if (value.length() > 150) return false;
        String[] parts = value.split("@", -1);
        if (parts.length != 2 || parts[0].length() > 64 || parts[0].startsWith(".")
                || parts[0].endsWith(".") || parts[0].contains("..")) return false;
        return parts[0].matches("[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+")
            && parts[1].matches("[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+");
    }
}
