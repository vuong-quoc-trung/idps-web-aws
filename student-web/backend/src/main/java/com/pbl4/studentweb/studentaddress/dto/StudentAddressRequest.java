package com.pbl4.studentweb.studentaddress.dto;

import com.pbl4.studentweb.studentaddress.entity.*;
import java.time.LocalDate;
import jakarta.validation.constraints.*;

/** Full replacement; optional fields may be cleared while a profile is incomplete. */
public record StudentAddressRequest(@NotNull AddressType addressType,
        @Size(max = 255) String addressLine,
        @Size(max = 100) String provinceCity,
        @Size(max = 100) String wardCommune,
        @Size(max = 50) String residenceRelation,
        @NotNull Boolean current, @Size(max = 2) String countryCode) {}
