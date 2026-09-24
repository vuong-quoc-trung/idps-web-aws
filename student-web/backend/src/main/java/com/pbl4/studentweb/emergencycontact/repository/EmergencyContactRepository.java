package com.pbl4.studentweb.emergencycontact.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import com.pbl4.studentweb.emergencycontact.entity.EmergencyContact;

public interface EmergencyContactRepository extends JpaRepository<EmergencyContact, Long> {
    java.util.List<EmergencyContact> findByStudentId(Long studentId);
}
