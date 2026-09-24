package com.pbl4.studentweb.user.entity;

import jakarta.persistence.*;
import java.time.LocalDate;
import java.time.LocalDateTime;
import lombok.Getter;
import lombok.Setter;
import com.pbl4.studentweb.common.entity.*;

@Getter
@Setter
@Entity
@Table(name = "users")
public class User extends AuditedEntity {
    @Column(name = "username", length = 50, nullable = false, unique = true)
    private String username;

    @Column(name = "password_hash", length = 255, nullable = false)
    private String passwordHash;

    @Enumerated(EnumType.STRING)
    @Column(name = "role", length = 20, nullable = false)
    private UserRole role;

    @org.hibernate.annotations.ColumnDefault("true")
    @Column(name = "enabled", nullable = false)
    private boolean enabled = true;

    @Column(name = "last_login_at")
    private LocalDateTime lastLoginAt;

    @org.hibernate.annotations.ColumnDefault("true")
    @Column(name = "password_setup_required", nullable = false)
    private boolean passwordSetupRequired = true;

    @Column(name = "activation_token_hash", length = 64, unique = true)
    private String activationTokenHash;

    @Column(name = "activation_expires_at")
    private LocalDateTime activationExpiresAt;
}
