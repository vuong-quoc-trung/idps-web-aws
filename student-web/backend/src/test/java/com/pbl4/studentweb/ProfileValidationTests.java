package com.pbl4.studentweb;

import com.pbl4.studentweb.common.catalog.*;
import com.pbl4.studentweb.common.validation.ContactValues;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;
import static org.assertj.core.api.Assertions.*;

class ProfileValidationTests {
    @Test void phoneNormalizationAndFormatValidation() {
        for (String value : new String[]{null, "", "0912345678", "0912 345 678", "+84 912-345-678", "02412345678", "+1 (415) 555-2671"})
            assertThat(ContactValues.validPhone(value)).as("valid %s", value).isTrue();
        for (String value : new String[]{"123", "0123456789", "+840912345678", "091234567a", "++84912345678", "+012345678", "+1234567890123456"})
            assertThat(ContactValues.validPhone(value)).as("invalid %s", value).isFalse();
        assertThat(ContactValues.phone(" +84 912-345-678 ")).isEqualTo("+84912345678");
    }
    @Test void emailValidationAllowsProvidersOtherThanGmailAndRejectsMalformedAddresses() {
        for (String value : new String[]{null, "", " test+tag@gmail.com ", "student@university.edu.vn", "a.b@outlook.com"})
            assertThat(ContactValues.validEmail(value)).as("valid %s", value).isTrue();
        for (String value : new String[]{"a@gmail", "a..b@gmail.com", ".a@gmail.com", "a @gmail.com", "a@@gmail.com", "a@-gmail.com", "a@gmail..com", "a".repeat(65)+"@gmail.com"})
            assertThat(ContactValues.validEmail(value)).as("invalid %s", value).isFalse();
    }
    @Test void catalogContainsEveryProvinceAndPreservesHierarchyAndLegacyValues() throws Exception {
        var service = new ProfileCatalogService(JsonMapper.builder().build());
        var d = service.catalog().divisions();
        assertThat(d.provinces()).hasSize(34);
        assertThat(d.historicalProvinces()).hasSize(63);
        var wards = d.provinces().stream().flatMap(p -> p.wards().stream()).toList();
        assertThat(wards).hasSizeGreaterThan(3000);
        assertThat(wards.stream().map(w -> w.code()).distinct().count()).isEqualTo(wards.size());
        assertThat(service.catalog().ethnicities()).hasSize(56).contains("Kinh", "Người nước ngoài");
        var dn = d.provinces().stream().filter(p -> p.code().equals("48")).findFirst().orElseThrow();
        var hn = d.provinces().stream().filter(p -> p.code().equals("01")).findFirst().orElseThrow();
        assertThat(service.province("Đà Nẵng", "VN", false, null)).isEqualTo(dn.name());
        assertThat(service.ward(dn.wards().getFirst().name(), dn.name(), "VN", null, false)).isEqualTo(dn.wards().getFirst().name());
        assertThatThrownBy(() -> service.ward(hn.wards().getFirst().name(), dn.name(), "VN", null, false)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> service.province("Fake Province", "VN", false, null)).isInstanceOf(IllegalArgumentException.class);
        assertThat(service.province("Quảng Nam", "VN", true, null)).isEqualTo("Tỉnh Quảng Nam");
        assertThat(service.province("Legacy location", "VN", false, "Legacy location")).isEqualTo("Legacy location");
        assertThat(service.province("California", "US", false, null)).isEqualTo("California");
        assertThat(service.ward("San Jose", "California", "US", null, false)).isEqualTo("San Jose");
        assertThatThrownBy(() -> service.country("XX")).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> service.choice("random", service.catalog().religions(), null, "Tôn giáo")).isInstanceOf(IllegalArgumentException.class);
    }
}
