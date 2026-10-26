package com.pbl4.studentweb.configuration;

import java.util.List;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

/** Capture the credential version when credentials are loaded for authentication. */
final class AccountPrincipal extends org.springframework.security.core.userdetails.User {
    private static final long serialVersionUID = 1L;
    private final long credentialVersion;
    private final Long userId;
    AccountPrincipal(com.pbl4.studentweb.user.entity.User user) {
        super(user.getUsername(), user.getPasswordHash(), user.isEnabled() && !user.isPasswordSetupRequired(),
            true, true, true, List.of(new SimpleGrantedAuthority("ROLE_" + user.getRole().name())));
        credentialVersion = user.getCredentialVersion();
        userId = user.getId();
    }
    long credentialVersion() { return credentialVersion; }
    Long userId() { return userId; }
}
