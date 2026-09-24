package com.pbl4.studentweb.studentclass.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import com.pbl4.studentweb.studentclass.entity.StudentClass;

public interface StudentClassRepository extends JpaRepository<StudentClass, Long> {
}
