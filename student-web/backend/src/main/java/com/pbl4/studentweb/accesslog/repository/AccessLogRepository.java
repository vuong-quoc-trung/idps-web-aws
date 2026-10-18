package com.pbl4.studentweb.accesslog.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import com.pbl4.studentweb.accesslog.entity.AccessLog;

public interface AccessLogRepository extends JpaRepository<AccessLog, Long> {
    @org.springframework.data.jpa.repository.Query("select a.id from AccessLog a where a.createdAt < :cutoff order by a.createdAt, a.id")
    java.util.List<Long> findExpiredIds(@org.springframework.data.repository.query.Param("cutoff") java.time.LocalDateTime cutoff,
            org.springframework.data.domain.Pageable pageable);

    @org.springframework.data.jpa.repository.Modifying
    @org.springframework.data.jpa.repository.Query("delete from AccessLog a where a.id in :ids and a.createdAt < :cutoff")
    int deleteExpiredIds(@org.springframework.data.repository.query.Param("ids") java.util.List<Long> ids,
            @org.springframework.data.repository.query.Param("cutoff") java.time.LocalDateTime cutoff);

}
