package com.pbl4.studentweb.studentaddress.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import com.pbl4.studentweb.studentaddress.entity.StudentAddress;

public interface StudentAddressRepository extends JpaRepository<StudentAddress, Long> {
    java.util.List<StudentAddress> findByStudentId(Long studentId);
}
