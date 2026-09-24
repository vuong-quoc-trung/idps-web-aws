package com.pbl4.studentweb.accesslog.mapper;

import com.pbl4.studentweb.accesslog.entity.AccessLog;
import com.pbl4.studentweb.accesslog.dto.AccessLogSummary;
import org.springframework.stereotype.Component;

@Component
public class AccessLogMapper {
    public AccessLogSummary toSummary(AccessLog e) {
        return new AccessLogSummary(e.getId(), e.getHttpMethod(), e.getRequestPath(), e.getStatusCode());
    }
}
