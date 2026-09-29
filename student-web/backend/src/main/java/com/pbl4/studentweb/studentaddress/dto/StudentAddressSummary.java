package com.pbl4.studentweb.studentaddress.dto;

import com.pbl4.studentweb.studentaddress.entity.*;
import java.time.LocalDate;

public record StudentAddressSummary(Long id, Long studentId, AddressType addressType, String addressLine, String provinceCity, String wardCommune, String residenceRelation, Boolean current) {}
