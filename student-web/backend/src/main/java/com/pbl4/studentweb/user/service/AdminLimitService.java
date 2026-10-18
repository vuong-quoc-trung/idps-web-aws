package com.pbl4.studentweb.user.service;

import com.pbl4.studentweb.user.entity.*;
import com.pbl4.studentweb.user.repository.UserRepository;
import jakarta.persistence.EntityManager;
import jakarta.persistence.LockModeType;
import org.springframework.stereotype.Service;
import org.springframework.transaction.*;
import org.springframework.transaction.annotation.*;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class AdminLimitService {
    private final EntityManager em;
    private final UserRepository users;
    private final TransactionTemplate initialize;
    public AdminLimitService(EntityManager em, UserRepository users, PlatformTransactionManager manager) {
        this.em = em; this.users = users;
        initialize = new TransactionTemplate(manager);
        initialize.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
    }
    @Transactional(propagation = Propagation.MANDATORY)
    public long lockAndCount() {
        try {
            initialize.executeWithoutResult(status -> {
                if (em.find(AdminCreationLock.class, 1) == null) {
                    em.persist(new AdminCreationLock(1)); em.flush();
                }
            });
        } catch (RuntimeException e) {
            // Another instance may have inserted the singleton. Recheck outside the failed transaction.
            if (!Boolean.TRUE.equals(initialize.execute(status -> em.find(AdminCreationLock.class, 1) != null))) throw e;
        }
        em.find(AdminCreationLock.class, 1, LockModeType.PESSIMISTIC_WRITE);
        return users.countByRole(UserRole.ADMIN);
    }
    @Transactional(propagation = Propagation.MANDATORY)
    public void requireSlot() {
        if (lockAndCount() >= 3)
            throw new IllegalStateException("Hệ thống chỉ cho phép tối đa 3 tài khoản Admin (bao gồm tài khoản bị khóa hoặc chưa kích hoạt).");
    }
}
