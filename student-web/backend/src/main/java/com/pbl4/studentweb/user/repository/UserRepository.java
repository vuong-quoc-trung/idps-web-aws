package com.pbl4.studentweb.user.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import com.pbl4.studentweb.user.entity.User;

public interface UserRepository extends JpaRepository<User, Long> {
    @org.springframework.data.jpa.repository.Lock(jakarta.persistence.LockModeType.PESSIMISTIC_WRITE)
    @org.springframework.data.jpa.repository.Query("select u from User u where u.activationTokenHash = :hash")
    java.util.Optional<User> findForActivation(@org.springframework.data.repository.query.Param("hash") String hash);
    java.util.Optional<User> findByUsername(String username);
    boolean existsByUsername(String username);
    boolean existsByRole(com.pbl4.studentweb.user.entity.UserRole role);

    @org.springframework.data.jpa.repository.Lock(jakarta.persistence.LockModeType.PESSIMISTIC_WRITE)
    @org.springframework.data.jpa.repository.Query("select u from User u where u.id = :id")
    java.util.Optional<User> findForUpdate(@org.springframework.data.repository.query.Param("id") Long id);
}
