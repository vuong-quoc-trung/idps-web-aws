package com.pbl4.studentweb;

import com.pbl4.studentweb.common.code.*;
import com.pbl4.studentweb.major.entity.Major;
import com.pbl4.studentweb.trainingprogram.entity.DegreeType;
import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import static org.assertj.core.api.Assertions.*;

@SpringBootTest(properties = {
    "spring.datasource.url=jdbc:h2:mem:codetests;MODE=PostgreSQL;DB_CLOSE_DELAY=-1",
    "spring.datasource.username=sa", "spring.datasource.password=",
    "spring.jpa.hibernate.ddl-auto=create-drop", "spring.jpa.properties.hibernate.default_schema=PUBLIC",
    "app.bootstrap.enabled=false", "logging.level.root=WARN"
})
class CodeGenerationTests {
    @Autowired CodeGenerationService codes;
    @Autowired CodeCounterAllocator allocator;
    @Autowired JdbcTemplate jdbc;
    @Autowired com.pbl4.studentweb.user.repository.UserRepository users;
    @Autowired org.springframework.transaction.PlatformTransactionManager transactionManager;

    @Test void normalizesAndMapsDegreesWithoutParsingEntityCodes() {
        var major = new Major(); major.setShortCode(" it "); major.setMajorCode("UNRELATED-LEGACY-CODE");
        assertThat(codes.faculty(" it ")).isEqualTo("FAC-IT");
        assertThat(codes.major(" se ")).isEqualTo("MAJ-SE");
        assertThat(codes.program(major, 2024, DegreeType.ENGINEER)).isEqualTo("PRG-IT-2024-ENG");
        assertThat(codes.program(major, 2024, DegreeType.BACHELOR)).isEqualTo("PRG-IT-2024-BSC");
        assertThat(codes.program(major, 2024, DegreeType.MASTER)).isEqualTo("PRG-IT-2024-MSC");
        for (String invalid : new String[]{"", "FAC-IT", "IT_SE", "123", "ABCDEFGHIJK", "ĐT"})
            assertThatThrownBy(() -> codes.faculty(invalid)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> codes.student(24)).isInstanceOf(IllegalArgumentException.class);
    }

    @Test void allocatesUniqueStudentCodesDuringConcurrentFirstUse() throws Exception {
        var start = new CountDownLatch(1);
        try (var pool = Executors.newFixedThreadPool(8)) {
            List<Future<String>> futures = new ArrayList<>();
            for (int i = 0; i < 32; i++) futures.add(pool.submit(() -> {
                start.await(); return codes.student(2081);
            }));
            start.countDown();
            Set<String> results = new HashSet<>();
            for (var future : futures) results.add(future.get(20, TimeUnit.SECONDS));
            assertThat(results).hasSize(32).contains("STU-2081-000001", "STU-2081-000032");
            assertThat(codes.student(2081)).isEqualTo("STU-2081-000033");
            assertThat(codes.student(2082)).isEqualTo("STU-2082-000001");
        }
    }

    @Test void classScopeIsMajorAndCohortAndSequenceExpandsBeyondTwoDigits() {
        var it = new Major(); it.setShortCode("IT");
        var se = new Major(); se.setShortCode("SE");
        assertThat(codes.studentClass(it, 2083)).isEqualTo("CLS-IT-2083-01");
        assertThat(codes.studentClass(it, 2083)).isEqualTo("CLS-IT-2083-02");
        assertThat(codes.studentClass(se, 2083)).isEqualTo("CLS-SE-2083-01");
        assertThat(codes.studentClass(it, 2084)).isEqualTo("CLS-IT-2084-01");
        jdbc.update("update code_counters set last_value = 99 where scope = ?", "CLS-IT-2083-");
        assertThat(codes.studentClass(it, 2083)).isEqualTo("CLS-IT-2083-100");
    }

    @Test void studentSequenceNeverExceedsSixDigits() {
        assertThat(codes.student(2085)).isEqualTo("STU-2085-000001");
        jdbc.update("update code_counters set last_value = 999998 where scope = ?", "STU-2085-");
        assertThat(codes.student(2085)).isEqualTo("STU-2085-999999");
        assertThatThrownBy(() -> codes.student(2085)).isInstanceOf(IllegalStateException.class);
    }
    @Test void skipsExistingLoginsAndDoesNotReuseReservationsAfterRollback() {
        var user = new com.pbl4.studentweb.user.entity.User();
        user.setUsername("STU-2086-000001"); user.setPasswordHash("not-a-login-password");
        user.setRole(com.pbl4.studentweb.user.entity.UserRole.STUDENT);
        users.saveAndFlush(user);
        assertThat(codes.student(2086)).isEqualTo("STU-2086-000002");
        var transaction = new org.springframework.transaction.support.TransactionTemplate(transactionManager);
        transaction.executeWithoutResult(status -> {
            assertThat(codes.student(2086)).isEqualTo("STU-2086-000003");
            status.setRollbackOnly();
        });
        assertThat(codes.student(2086)).isEqualTo("STU-2086-000004");
        assertThat(jdbc.queryForObject("select last_value from code_counters where scope = ?", Long.class, "STU-2086-"))
                .isEqualTo(4L);
    }

    @Test void allocatesUniqueClassCodesConcurrently() throws Exception {
        var major = new Major(); major.setShortCode("CONCURRENT");
        var start = new CountDownLatch(1);
        try (var pool = Executors.newFixedThreadPool(8)) {
            List<Future<String>> futures = new ArrayList<>();
            for (int i = 0; i < 24; i++) futures.add(pool.submit(() -> {
                start.await(); return codes.studentClass(major, 2087);
            }));
            start.countDown();
            Set<String> results = new HashSet<>();
            for (var future : futures) results.add(future.get(20, TimeUnit.SECONDS));
            assertThat(results).hasSize(24).contains("CLS-CONCURRENT-2087-01", "CLS-CONCURRENT-2087-24");
        }
    }

}
