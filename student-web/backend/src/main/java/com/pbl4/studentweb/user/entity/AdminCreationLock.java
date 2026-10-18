package com.pbl4.studentweb.user.entity;

import jakarta.persistence.*;

/** Singleton row serializes admin creation across backend instances. */
@Entity
@Table(name = "admin_creation_lock")
public class AdminCreationLock {
    @Id
    private Integer id;
    protected AdminCreationLock() {}
    public AdminCreationLock(int id) { this.id = id; }
}
