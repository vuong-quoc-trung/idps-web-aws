package com.pbl4.studentweb.postgraduationcontact.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import com.pbl4.studentweb.postgraduationcontact.entity.PostGraduationContact;

public interface PostGraduationContactRepository extends JpaRepository<PostGraduationContact, Long> {
    java.util.List<PostGraduationContact> findByStudentId(Long studentId);
}
