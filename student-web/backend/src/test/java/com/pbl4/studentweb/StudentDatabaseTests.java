package com.pbl4.studentweb;

import com.pbl4.studentweb.student.dto.*;
import com.pbl4.studentweb.student.entity.*;
import com.pbl4.studentweb.student.repository.StudentRepository;
import com.pbl4.studentweb.student.service.*;
import com.pbl4.studentweb.user.repository.UserRepository;
import com.pbl4.studentweb.user.service.PasswordSetupService;
import com.pbl4.studentweb.major.entity.Major;
import com.pbl4.studentweb.major.repository.MajorRepository;
import com.pbl4.studentweb.trainingprogram.entity.TrainingProgram;
import com.pbl4.studentweb.trainingprogram.repository.TrainingProgramRepository;
import com.pbl4.studentweb.studentclass.entity.StudentClass;
import com.pbl4.studentweb.studentclass.repository.StudentClassRepository;
import com.pbl4.studentweb.studentaddress.entity.*;
import com.pbl4.studentweb.studentaddress.repository.StudentAddressRepository;
import com.pbl4.studentweb.familymember.entity.*;
import com.pbl4.studentweb.familymember.repository.FamilyMemberRepository;
import com.pbl4.studentweb.emergencycontact.entity.EmergencyContact;
import com.pbl4.studentweb.emergencycontact.repository.EmergencyContactRepository;
import java.time.LocalDate;
import java.time.LocalDateTime;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.jdbc.core.JdbcTemplate;
import static org.assertj.core.api.Assertions.*;

@SpringBootTest(properties = {
    "spring.datasource.url=jdbc:h2:mem:studenttests;MODE=PostgreSQL;DB_CLOSE_DELAY=-1",
    "spring.datasource.username=sa", "spring.datasource.password=",
    "spring.jpa.hibernate.ddl-auto=create-drop", "spring.jpa.properties.hibernate.default_schema=PUBLIC"
})
@Transactional
class StudentDatabaseTests {
    @Autowired StudentOnboardingService onboarding;
    @Autowired StudentProfileCompletionService completion;
    @Autowired PasswordSetupService passwords;
    @Autowired StudentRepository students;
    @Autowired UserRepository users;
    @Autowired MajorRepository majors;
    @Autowired StudentClassRepository classes;
    @Autowired TrainingProgramRepository programs;
    @Autowired StudentAddressRepository addresses;
    @Autowired FamilyMemberRepository relatives;
    @Autowired EmergencyContactRepository emergency;
    @Autowired PasswordEncoder encoder;
    @Autowired JdbcTemplate jdbc;

    StudentOnboardingResult create() {
        Major m = new Major(); m.setMajorCode("TEST"); m.setMajorName("Test major"); majors.save(m);
        TrainingProgram p = new TrainingProgram(); p.setProgramCode("TEST24"); p.setProgramName("Test program");
        p.setMajor(m); programs.save(p);
        StudentClass c = new StudentClass(); c.setClassCode("TEST_CLASS"); c.setMajor(m); c.setProgram(p); classes.save(c);
        return onboarding.create(new CreateStudentRequest("TEST001", "Test Student", LocalDate.of(2006, 1, 1),
                Gender.OTHER, "TEST_CITIZEN", m.getId(), c.getId(), p.getId(), null, null, null));
    }

    @Test void generatesAllTablesAndForeignKeys() {
        assertThat(jdbc.queryForList("select table_name from information_schema.tables where table_schema = 'PUBLIC'", String.class))
                .contains("USERS", "MAJORS", "TRAINING_PROGRAMS", "CLASSES", "STUDENTS", "STUDENT_ADDRESSES",
                        "FAMILY_MEMBERS", "EMERGENCY_CONTACTS", "POST_GRADUATION_CONTACTS", "ACCESS_LOGS");
        assertThat(jdbc.queryForObject("select count(*) from information_schema.table_constraints where constraint_type = 'FOREIGN KEY' and table_schema = 'PUBLIC'", Integer.class))
                .isEqualTo(13);
        assertThat(jdbc.queryForList("select column_name from information_schema.columns where table_name = 'STUDENTS'", String.class))
                .doesNotContain("PASSWORD", "PASSWORD_HASH", "OFFICE365_INITIAL_PASSWORD");
    }

    @Test void createsIncompleteAccountAndConsumesActivationTokenOnce() {
        var result = create();
        Student student = students.findById(result.student().id()).orElseThrow();
        assertThat(student.getProfileStatus()).isEqualTo(ProfileStatus.INCOMPLETE);
        assertThat(completion.refresh(student.getId()).missingFields()).contains("personalEmail", "currentAddress", "mother");
        var user = student.getUser();
        assertThat(user.isPasswordSetupRequired()).isTrue();
        assertThat(user.getActivationTokenHash()).isNotEqualTo(result.activationToken());
        passwords.setInitialPassword(result.activationToken(), "A-good-test-password");
        assertThat(encoder.matches("A-good-test-password", user.getPasswordHash())).isTrue();
        assertThat(user.isPasswordSetupRequired()).isFalse();
        assertThat(user.getActivationTokenHash()).isNull();
        assertThatThrownBy(() -> passwords.setInitialPassword(result.activationToken(), "Another-good-password"))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test void rejectsExpiredAndInvalidTokens() {
        var result = create();
        var user = students.findById(result.student().id()).orElseThrow().getUser();
        user.setActivationExpiresAt(LocalDateTime.now().minusSeconds(1));
        assertThatThrownBy(() -> passwords.setInitialPassword(result.activationToken(), "A-good-test-password"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> passwords.setInitialPassword("unknown", "A-good-test-password"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThat(user.isPasswordSetupRequired()).isTrue();
    }

    @Test void completesProfileWithoutOptionalFieldsAndRevertsWhenRequiredSectionRemoved() {
        var result = create();
        var s = students.findById(result.student().id()).orElseThrow();
        s.setPlaceOfBirth("Test city"); s.setEthnicity("Test"); s.setNationality("Test");
        s.setCitizenIdIssueDate(LocalDate.of(2022, 1, 1));
        s.setHealthInsuranceNumber("TEST_INSURANCE"); s.setHealthInsuranceExpiry(LocalDate.now().plusYears(1));
        s.setPersonalEmail("student@example.invalid"); s.setPhoneNumber("0900000000");
        for (var type : new AddressType[]{AddressType.CURRENT, AddressType.FAMILY_HOME}) {
            StudentAddress a = new StudentAddress(); a.setStudent(s); a.setAddressType(type);
            a.setAddressLine("Test street"); a.setProvinceCity("Test city"); a.setWardCommune("Test ward"); addresses.save(a);
        }
        for (var role : new FamilyRelationship[]{FamilyRelationship.MOTHER, FamilyRelationship.FATHER}) {
            FamilyMember f = new FamilyMember(); f.setStudent(s); f.setRelationship(role); f.setUnavailable(true); relatives.save(f);
        }
        EmergencyContact e = new EmergencyContact(); e.setStudent(s); e.setFullName("Test contact");
        e.setPhoneNumber("0900000001"); emergency.save(e);
        assertThat(completion.refresh(s.getId()).status()).isEqualTo(ProfileStatus.COMPLETE);
        var completedAt = s.getProfileCompletedAt();
        assertThat(completedAt).isNotNull();
        completion.refresh(s.getId());
        assertThat(s.getProfileCompletedAt()).isEqualTo(completedAt);
        addresses.findByStudentId(s.getId()).forEach(a -> a.setCurrent(false));
        assertThat(completion.refresh(s.getId()).status()).isEqualTo(ProfileStatus.INCOMPLETE);
        assertThat(s.getProfileCompletedAt()).isNull();
    }

    @Test void rejectsClassFromAnotherMajorAndRollsBackAccountCreation() {
        create();
        Major other = new Major(); other.setMajorCode("OTHER"); other.setMajorName("Other"); majors.save(other);
        var c = classes.findAll().getFirst();
        assertThatThrownBy(() -> onboarding.create(new CreateStudentRequest("TEST002", "Test Student", null,
                null, null, other.getId(), c.getId(), null, null, null, null))).isInstanceOf(IllegalArgumentException.class);
        assertThat(users.count()).isEqualTo(1);
    }
}
