package com.pbl4.studentweb.accesslog.service;

import com.pbl4.studentweb.accesslog.repository.AccessLogRepository;
import com.pbl4.studentweb.accesslog.mapper.AccessLogMapper;
import com.pbl4.studentweb.accesslog.dto.AccessLogSummary;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class AccessLogService {
    private final AccessLogRepository repository;
    private final AccessLogMapper mapper;

    // Internal service only; caller authorization belongs to the future API layer.
    public Page<AccessLogSummary> findAll(Pageable pageable) {
        return repository.findAll(pageable).map(mapper::toSummary);
    }
}
