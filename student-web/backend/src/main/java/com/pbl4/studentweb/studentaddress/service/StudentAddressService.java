package com.pbl4.studentweb.studentaddress.service;

import com.pbl4.studentweb.studentaddress.repository.StudentAddressRepository;
import com.pbl4.studentweb.studentaddress.mapper.StudentAddressMapper;
import com.pbl4.studentweb.studentaddress.entity.StudentAddress;
import com.pbl4.studentweb.studentaddress.dto.*;
import com.pbl4.studentweb.student.repository.StudentRepository;
import com.pbl4.studentweb.student.service.StudentProfileCompletionService;
import com.pbl4.studentweb.common.exception.ResourceNotFoundException;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import java.util.List;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import static com.pbl4.studentweb.common.validation.TextValues.optional;

@Service
@Validated
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class StudentAddressService {
    private final com.pbl4.studentweb.common.catalog.ProfileCatalogService catalogs;
    private final StudentAddressRepository repository;
    private final StudentAddressMapper mapper;
    private final StudentRepository students;
    private final StudentProfileCompletionService completion;

    // Internal operation; the API exposes only student-scoped reads.
    public Page<StudentAddressSummary> findAll(Pageable pageable) {
        return repository.findAll(pageable).map(mapper::toSummary);
    }
    public List<StudentAddressSummary> findByStudentId(Long studentId) {
        if (!students.existsById(studentId)) throw new ResourceNotFoundException("Student");
        return repository.findByStudentId(studentId).stream().map(mapper::toSummary).toList();
    }
    public StudentAddressSummary findById(Long studentId, Long id) { return mapper.toSummary(require(studentId, id)); }

    @Transactional
    public StudentAddressSummary create(Long studentId, @NotNull @Valid StudentAddressRequest request) {
        var student = students.findById(studentId).orElseThrow(() -> new ResourceNotFoundException("Student"));
        var entity = new StudentAddress();
        entity.setStudent(student);
        apply(entity, request);
        repository.saveAndFlush(entity);
        completion.refresh(studentId);
        return mapper.toSummary(entity);
    }
    @Transactional
    public StudentAddressSummary update(Long studentId, Long id, @NotNull @Valid StudentAddressRequest request) {
        var entity = require(studentId, id);
        apply(entity, request);
        repository.saveAndFlush(entity);
        completion.refresh(studentId);
        return mapper.toSummary(entity);
    }
    @Transactional
    public void delete(Long studentId, Long id) {
        repository.delete(require(studentId, id));
        repository.flush();
        completion.refresh(studentId);
    }
    private StudentAddress require(Long studentId, Long id) {
        return repository.findByIdAndStudentId(id, studentId)
                .orElseThrow(() -> new ResourceNotFoundException("StudentAddress"));
    }
    private void apply(StudentAddress e, StudentAddressRequest r) {
        e.setAddressType(r.addressType());
        e.setAddressLine(optional(r.addressLine()));
        String country = catalogs.country(r.countryCode());
        String province = catalogs.province(r.provinceCity(), country, false,
                country.equals(e.getCountryCode()) ? e.getProvinceCity() : null);
        String ward = catalogs.ward(r.wardCommune(), province, country, e.getWardCommune(),
                country.equals(e.getCountryCode()) && java.util.Objects.equals(province,
                    catalogs.province(e.getProvinceCity(), country, false, e.getProvinceCity())));
        e.setCountryCode(country);
        e.setProvinceCity(province);
        e.setWardCommune(ward);
        e.setResidenceRelation(catalogs.choice(r.residenceRelation(), catalogs.catalog().residenceRelations(), e.getResidenceRelation(), "Quan hệ với nơi ở"));
        e.setCurrent(r.current());
    }
}
