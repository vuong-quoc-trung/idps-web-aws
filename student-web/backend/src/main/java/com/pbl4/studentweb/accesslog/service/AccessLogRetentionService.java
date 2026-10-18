package com.pbl4.studentweb.accesslog.service;

import com.pbl4.studentweb.accesslog.repository.AccessLogRepository;
import java.time.LocalDateTime;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
public class AccessLogRetentionService {
    public static final int BATCH_SIZE = 500;
    private final AccessLogRepository repository;

    /** Each invocation commits one bounded batch; the scheduler holds no outer transaction. */
    @Transactional
    public int deleteBatch(LocalDateTime cutoff) {
        var ids = repository.findExpiredIds(cutoff, PageRequest.of(0, BATCH_SIZE));
        return ids.isEmpty() ? 0 : repository.deleteExpiredIds(ids, cutoff);
    }
}
