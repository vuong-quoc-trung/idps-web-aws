package com.pbl4.studentweb.accesslog.entity;

import jakarta.persistence.*;
import java.time.LocalDate;
import java.time.LocalDateTime;
import lombok.Getter;
import lombok.Setter;
import com.pbl4.studentweb.common.entity.*;
import com.pbl4.studentweb.user.entity.User;

@Getter
@Setter
@Entity
@Table(name = "access_logs", indexes = {@Index(name = "idx_access_logs_created_at", columnList = "created_at"), @Index(name = "idx_access_logs_user_id", columnList = "user_id"), @Index(name = "idx_access_logs_client_ip", columnList = "client_ip")})
public class AccessLog extends BaseEntity {
    @ManyToOne(fetch = FetchType.LAZY, optional = true)
    @JoinColumn(name = "user_id", nullable = true)
    private User user;

    @Column(name = "client_ip", length = 45)
    private String clientIp;

    @Column(name = "http_method", length = 10, nullable = false)
    private String httpMethod;

    @Column(name = "request_path", length = 500, nullable = false)
    private String requestPath;

    @Column(name = "status_code")
    private Integer statusCode;

    @Column(name = "action", length = 100)
    private String action;

    @Column(name = "user_agent", columnDefinition = "text")
    private String userAgent;

    @Column(name = "request_time_ms")
    private Long requestTimeMs;

    @org.hibernate.annotations.CreationTimestamp
    @Column(name = "created_at", nullable = false)
    private LocalDateTime createdAt;
}
