package com.pbl4.studentweb.accesslog.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import com.pbl4.studentweb.accesslog.entity.AccessLog;

public interface AccessLogRepository extends JpaRepository<AccessLog, Long> {
}
