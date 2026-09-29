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
    @Autowired com.pbl4.studentweb.faculty.repository.FacultyRepository faculties;
    com.pbl4.studentweb.faculty.entity.Faculty faculty;

    @org.junit.jupiter.api.BeforeEach void createFaculty() {
        faculty = new com.pbl4.studentweb.faculty.entity.Faculty();
        faculty.setFacultyCode("TEST_FAC"); faculty.setFacultyName("Test faculty"); faculties.saveAndFlush(faculty);
    }
    @Autowired StudentClassRepository classes;
    @Autowired TrainingProgramRepository programs;
    @Autowired StudentAddressRepository addresses;
    @Autowired FamilyMemberRepository relatives;
    @Autowired EmergencyContactRepository emergency;
    @Autowired PasswordEncoder encoder;
    @Autowired JdbcTemplate jdbc;

    StudentOnboardingResult create() {
        Major m = new Major(); m.setMajorCode("TEST"); m.setMajorName("Test major"); m.setFaculty(faculty); majors.save(m);
        TrainingProgram p = new TrainingProgram(); p.setProgramCode("TEST24"); p.setProgramName("Test program");
        p.setMajor(m); programs.save(p);
        StudentClass c = new StudentClass(); c.setClassCode("TEST_CLASS"); c.setMajor(m); c.setProgram(p); classes.save(c);
        return onboarding.create(new CreateStudentRequest("TEST001", "Test Student", LocalDate.of(2006, 1, 1),
                Gender.OTHER, "TEST_CITIZEN", m.getId(), c.getId(), p.getId(), null, null, null));
    }

    @Test void generatesAllTablesAndForeignKeys() {
        assertThat(jdbc.queryForList("select table_name from information_schema.tables where table_schema = 'PUBLIC'", String.class))
                .contains("USERS", "FACULTIES", "MAJORS", "TRAINING_PROGRAMS", "CLASSES", "STUDENTS", "STUDENT_ADDRESSES",
                        "FAMILY_MEMBERS", "EMERGENCY_CONTACTS", "POST_GRADUATION_CONTACTS", "ACCESS_LOGS");
        assertThat(jdbc.queryForObject("select count(*) from information_schema.table_constraints where constraint_type = 'FOREIGN KEY' and table_schema = 'PUBLIC'", Integer.class))
                .isEqualTo(14);
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
        Major other = new Major(); other.setMajorCode("OTHER"); other.setMajorName("Other"); other.setFaculty(faculty); majors.save(other);
        var c = classes.findAll().getFirst();
        assertThatThrownBy(() -> onboarding.create(new CreateStudentRequest("TEST002", "Test Student", null,
                null, null, other.getId(), c.getId(), null, null, null, null))).isInstanceOf(IllegalArgumentException.class);
        assertThat(users.count()).isEqualTo(1);
    }

    @Test void academicParentColumnsAreRequiredInTheSchema() {
        for (String[] column : new String[][] {
                {"MAJORS", "FACULTY_ID"}, {"TRAINING_PROGRAMS", "MAJOR_ID"}, {"CLASSES", "PROGRAM_ID"},
                {"STUDENTS", "CLASS_ID"}, {"STUDENTS", "TRAINING_PROGRAM_ID"}, {"STUDENTS", "MAJOR_ID"}}) {
            assertThat(jdbc.queryForObject(
                    "select is_nullable from information_schema.columns where table_schema = 'PUBLIC' and table_name = ? and column_name = ?",
                    String.class, column[0], column[1])).isEqualTo("NO");
        }
    }
    @Test void databaseRejectsInvalidAcademicNumbersWithoutApiValidation() {
        create();
        for (String assignment : new String[]{
                "number_of_semesters = 0", "number_of_semesters = -1",
                "total_credits = -1", "required_credits = -1", "elective_credits = -1",
                "total_credits = 10, required_credits = 11",
                "total_credits = 10, elective_credits = 11",
                "total_credits = 10, required_credits = 6, elective_credits = 3",
                "total_credits = 10, required_credits = 6, elective_credits = 5",
                "total_credits = 2147483647, required_credits = 2147483647, elective_credits = 2147483647"}) {
            assertThatThrownBy(() -> jdbc.update("update training_programs set " + assignment))
                    .as(assignment).isInstanceOf(org.springframework.dao.DataIntegrityViolationException.class);
        }
        assertThat(jdbc.update("update training_programs set number_of_semesters = 1, total_credits = 0, required_credits = 0, elective_credits = 0"))
                .isEqualTo(1);
        assertThat(jdbc.update("update training_programs set total_credits = 140, required_credits = 110, elective_credits = 30"))
                .isEqualTo(1);
    }

    @Test void databaseEnforcesUniqueMajorAndProgramCodes() {
        create();
        assertThatThrownBy(() -> jdbc.update(
                "insert into majors (major_code, major_name, faculty_id, active) select major_code, major_name, faculty_id, active from majors"))
                .isInstanceOf(org.springframework.dao.DataIntegrityViolationException.class);
        assertThatThrownBy(() -> jdbc.update(
                "insert into training_programs (program_code, program_name, major_id, active) select program_code, program_name, major_id, active from training_programs"))
                .isInstanceOf(org.springframework.dao.DataIntegrityViolationException.class);
    }

}
