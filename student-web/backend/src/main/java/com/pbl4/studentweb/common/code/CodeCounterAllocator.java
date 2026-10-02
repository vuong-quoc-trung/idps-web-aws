package com.pbl4.studentweb.common.code;

import jakarta.persistence.EntityManager;
import jakarta.persistence.LockModeType;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

/** Each reservation commits independently: failed business transactions may leave gaps. */
@Service
public class CodeCounterAllocator {
    private final EntityManager em;
    private final TransactionTemplate transaction;

    public CodeCounterAllocator(EntityManager em, PlatformTransactionManager manager) {
        this.em = em;
        this.transaction = new TransactionTemplate(manager);
        this.transaction.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
    }

    public long next(String scope, long maximum) {
        try {
            transaction.executeWithoutResult(status -> {
                if (em.find(CodeCounter.class, scope) == null) {
                    em.persist(new CodeCounter(scope));
                    em.flush();
                }
            });
        } catch (RuntimeException creationFailure) {
            // Concurrent first use can win the PK insert. Verify in a fresh transaction;
            // never continue inside a transaction aborted by PostgreSQL.
            Boolean exists = transaction.execute(status -> em.find(CodeCounter.class, scope) != null);
            if (!Boolean.TRUE.equals(exists)) throw creationFailure;
        }
        return transaction.execute(status -> {
            var counter = em.find(CodeCounter.class, scope, LockModeType.PESSIMISTIC_WRITE);
            if (counter.getLastValue() >= maximum)
                throw new IllegalStateException("Code sequence exhausted for " + scope);
            long next = counter.getLastValue() + 1;
            counter.setLastValue(next);
            em.flush();
            return next;
        });
    }
}
