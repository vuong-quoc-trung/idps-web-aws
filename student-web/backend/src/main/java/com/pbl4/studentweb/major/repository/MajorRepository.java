package com.pbl4.studentweb.major.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import com.pbl4.studentweb.major.entity.Major;

public interface MajorRepository extends JpaRepository<Major, Long> {
}
