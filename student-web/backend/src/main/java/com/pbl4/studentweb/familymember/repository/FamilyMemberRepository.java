package com.pbl4.studentweb.familymember.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import com.pbl4.studentweb.familymember.entity.FamilyMember;

public interface FamilyMemberRepository extends JpaRepository<FamilyMember, Long> {
    java.util.List<FamilyMember> findByStudentId(Long studentId);
}
