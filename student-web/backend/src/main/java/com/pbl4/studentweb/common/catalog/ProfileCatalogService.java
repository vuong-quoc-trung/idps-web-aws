package com.pbl4.studentweb.common.catalog;

import java.io.IOException;
import java.util.*;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Service;
import tools.jackson.databind.json.JsonMapper;
import static com.pbl4.studentweb.common.validation.TextValues.optional;

@Service
public class ProfileCatalogService {
    public record Option(String code, String name) {}
    public record Province(String code, String name, List<Option> wards) {}
    public record Divisions(String provinceCheckedAt, String wardEffectiveDate, String source,
            String provinceSource, String sourceSha256, String wardCheckedAt, String wardSource, List<Province> provinces, List<Option> historicalProvinces) {}
    public record Catalog(Divisions divisions, List<Option> countries, List<String> ethnicities,
            List<String> religions, List<String> residenceRelations) {}
    private final Catalog catalog;
    public ProfileCatalogService(JsonMapper mapper) throws IOException {
        try (var input = new ClassPathResource("catalogs/vietnam-divisions.json").getInputStream()) {
            var divisions = mapper.readValue(input, Divisions.class);
            var vi = Locale.forLanguageTag("vi");
            var countries = Arrays.stream(Locale.getISOCountries())
                .map(code -> new Option(code, new Locale.Builder().setRegion(code).build().getDisplayCountry(vi)))
                .sorted(Comparator.comparing(Option::name)).toList();
            catalog = new Catalog(divisions, countries,
                Arrays.stream(Ethnicity.values()).map(Ethnicity::label).toList(),
                Arrays.stream(Religion.values()).map(Religion::label).toList(),
                Arrays.stream(ResidenceRelation.values()).map(ResidenceRelation::label).toList());
        }
    }
    public Catalog catalog() { return catalog; }
    public String country(String code) {
        String value = optional(code);
        value = value == null ? "VN" : value.toUpperCase(Locale.ROOT);
        final String result = value;
        if (catalog.countries().stream().noneMatch(c -> c.code().equals(result)))
            throw new IllegalArgumentException("Quốc gia không hợp lệ");
        return result;
    }
    public String choice(String value, List<String> options, String previous, String field) {
        String text = optional(value);
        if (text == null) return null;
        for (var option : options) if (option.equalsIgnoreCase(text)) return option;
        if (Objects.equals(text, optional(previous))) return text; // Preserve unchanged legacy data only.
        throw new IllegalArgumentException(field + ": vui lòng chọn giá trị trong danh sách");
    }
    private String shortName(String value) {
        return value.replaceFirst("^(Thành phố|Tỉnh) ", "");
    }
    public String province(String value, String countryCode, boolean historical, String previous) {
        String text = optional(value);
        if (text == null || !"VN".equals(countryCode)) return text;
        var options = new ArrayList<Option>();
        catalog.divisions().provinces().forEach(p -> options.add(new Option(p.code(), p.name())));
        if (historical) options.addAll(catalog.divisions().historicalProvinces());
        for (var option : options)
            if (option.name().equalsIgnoreCase(text) || shortName(option.name()).equalsIgnoreCase(text)) return option.name();
        if (Objects.equals(text, optional(previous))) return text;
        throw new IllegalArgumentException("Tỉnh/thành phố không thuộc danh mục Việt Nam");
    }
    public String ward(String value, String province, String countryCode, String previous, boolean sameParent) {
        String text = optional(value);
        if (text == null || !"VN".equals(countryCode)) return text;
        var parent = catalog.divisions().provinces().stream().filter(p -> p.name().equals(province)).findFirst();
        if (parent.isPresent() && parent.get().wards().stream().anyMatch(w -> w.name().equals(text))) return text;
        if (sameParent && Objects.equals(text, optional(previous))) return text;
        throw new IllegalArgumentException("Xã/phường/đặc khu không thuộc tỉnh/thành phố đã chọn");
    }
}
