package com.pbl4.studentweb.common.catalog;

import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;
@RestController
@RequiredArgsConstructor
@RequestMapping("/api/profile-options")
public class ProfileCatalogController {
    private final ProfileCatalogService service;
    @GetMapping public ProfileCatalogService.Catalog options() { return service.catalog(); }
}
