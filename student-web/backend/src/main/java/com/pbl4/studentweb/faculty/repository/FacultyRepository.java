package com.pbl4.studentweb.faculty.repository;

import com.pbl4.studentweb.faculty.entity.Faculty;
import org.springframework.data.jpa.repository.JpaRepository;

public interface FacultyRepository extends JpaRepository<Faculty, Long> {
    boolean existsByFacultyCode(String code);
    boolean existsByFacultyCodeAndIdNot(String code, Long id);
}
