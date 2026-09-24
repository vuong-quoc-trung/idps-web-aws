package com.pbl4.studentweb.student.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import com.pbl4.studentweb.student.entity.Student;

public interface StudentRepository extends JpaRepository<Student, Long> {
    java.util.Optional<Student> findByUserId(Long userId);
}
