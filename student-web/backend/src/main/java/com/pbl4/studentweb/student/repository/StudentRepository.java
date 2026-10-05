package com.pbl4.studentweb.student.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import com.pbl4.studentweb.student.entity.Student;

public interface StudentRepository extends JpaRepository<Student, Long>, org.springframework.data.jpa.repository.JpaSpecificationExecutor<Student> {
    java.util.Optional<Student> findByUserId(Long userId);
    java.util.Optional<Student> findByStudentCode(String studentCode);
    boolean existsByStudentCode(String code);
    boolean existsByCitizenIdAndIdNot(String citizenId, Long id);
    boolean existsBySchoolEmail(String email);
    boolean existsByMajorId(Long majorId);
    boolean existsByStudentClassId(Long classId);
    boolean existsByTrainingProgramIdOrSecondaryProgramId(Long primaryId, Long secondaryId);
}
