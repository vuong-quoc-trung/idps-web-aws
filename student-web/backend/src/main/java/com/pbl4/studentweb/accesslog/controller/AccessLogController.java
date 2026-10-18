package com.pbl4.studentweb.accesslog.controller;

import com.pbl4.studentweb.accesslog.dto.AccessLogSummary;
import com.pbl4.studentweb.accesslog.service.AccessLogService;
import com.pbl4.studentweb.common.web.PageResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

/** Audit records are read-only through this API. */
@RestController
@RequiredArgsConstructor
@RequestMapping("/api/access-logs")
public class AccessLogController {
    private final AccessLogService service;
    @GetMapping
    public PageResponse<AccessLogSummary> list(@RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size,
            @RequestParam(defaultValue = "DESC") org.springframework.data.domain.Sort.Direction direction) {
        var pagination = PageResponse.request(page, size);
        var sorted = org.springframework.data.domain.PageRequest.of(pagination.getPageNumber(), pagination.getPageSize(),
                org.springframework.data.domain.Sort.by(direction, "createdAt", "id"));
        return PageResponse.from(service.findAll(sorted));
    }
    @GetMapping("/{id}")
    public AccessLogSummary get(@PathVariable Long id) { return service.findById(id); }
}
