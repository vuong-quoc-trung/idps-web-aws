package com.pbl4.studentweb;

import com.pbl4.studentweb.emergencycontact.repository.EmergencyContactRepository;
import com.pbl4.studentweb.major.entity.Major;
import com.pbl4.studentweb.major.repository.MajorRepository;
import com.pbl4.studentweb.student.entity.*;
import com.pbl4.studentweb.student.repository.StudentRepository;
import com.pbl4.studentweb.studentclass.entity.StudentClass;
import com.pbl4.studentweb.studentclass.repository.StudentClassRepository;
import com.pbl4.studentweb.trainingprogram.entity.TrainingProgram;
import com.pbl4.studentweb.trainingprogram.repository.TrainingProgramRepository;
import com.pbl4.studentweb.user.entity.*;
import com.pbl4.studentweb.user.repository.UserRepository;
import java.time.LocalDate;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.context.WebApplicationContext;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;
import static org.assertj.core.api.Assertions.*;
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties = {
    "spring.datasource.url=jdbc:h2:mem:apitests;MODE=PostgreSQL;DB_CLOSE_DELAY=-1",
    "spring.datasource.username=sa", "spring.datasource.password=",
    "spring.jpa.hibernate.ddl-auto=create-drop", "spring.jpa.properties.hibernate.default_schema=PUBLIC",
    "app.bootstrap.enabled=false", "logging.level.root=WARN"
})
@Transactional
class StudentApiTests {
    private static final String PASSWORD = "A-good-test-password";
    @Autowired WebApplicationContext context;
    @Autowired JsonMapper json;
    @Autowired UserRepository users;
    @Autowired StudentRepository students;
    @Autowired MajorRepository majors;
    @Autowired com.pbl4.studentweb.faculty.repository.FacultyRepository faculties;
    com.pbl4.studentweb.faculty.entity.Faculty faculty;
    @Autowired StudentClassRepository classes;
    @Autowired TrainingProgramRepository programs;
    @Autowired EmergencyContactRepository contacts;
    @Autowired PasswordEncoder encoder;
    MockMvc mvc;
    String hash;
    User admin;
    StudentClass studentClass;

    @BeforeEach void setup() {
        mvc = MockMvcBuilders.webAppContextSetup(context).apply(springSecurity()).build();
        faculty = new com.pbl4.studentweb.faculty.entity.Faculty();
        faculty.setFacultyCode("FAC"); faculty.setFacultyName("Test faculty"); faculties.saveAndFlush(faculty);
        hash = encoder.encode(PASSWORD);
        admin = account("admin-test", UserRole.ADMIN);
        account("staff-test", UserRole.STAFF);
    }
    User account(String username, UserRole role) {
        var user = new User();
        user.setUsername(username); user.setRole(role); user.setPasswordHash(hash); user.setPasswordSetupRequired(false);
        return users.saveAndFlush(user);
    }
    StudentClass catalog() {
        if (studentClass != null) return studentClass;
        var major = new Major(); major.setMajorCode("MAJ-CS"); major.setShortCode("CS"); major.setMajorName("Computer science"); major.setFaculty(faculty); majors.save(major);
        var program = new TrainingProgram(); program.setProgramCode("CS2026"); program.setProgramName("Program");
        program.setMajor(major); program.setCohort(2026); program.setDegreeType(com.pbl4.studentweb.trainingprogram.entity.DegreeType.ENGINEER); programs.save(program);
        studentClass = new StudentClass(); studentClass.setClassCode("CS26"); studentClass.setMajor(major);
        studentClass.setProgram(program); studentClass.setCohort(2026); return classes.saveAndFlush(studentClass);
    }
    Student student(String code) {
        var group = catalog(); var student = new Student();
        student.setSchoolEmail(code.toLowerCase(java.util.Locale.ROOT).replace("-", "") + "@sv.pbl4.edu.vn");
        student.setStudentCode(code); student.setFullName("Student " + code); student.setUser(account(code, UserRole.STUDENT));
        student.setMajor(group.getMajor()); student.setStudentClass(group); student.setTrainingProgram(group.getProgram());
        student.setDateOfBirth(LocalDate.of(2006, 1, 1)); student.setGender(Gender.OTHER); student.setCitizenId("ID-" + code);
        return students.saveAndFlush(student);
    }
    MockHttpSession login(String username) throws Exception {
        return (MockHttpSession) mvc.perform(post("/api/auth/login").with(csrf())
                .param("username", username).param("password", PASSWORD))
                .andExpect(status().isNoContent()).andReturn().getRequest().getSession(false);
    }
    JsonNode body(MvcResult result) throws Exception { return json.readTree(result.getResponse().getContentAsString()); }
    MvcResult send(MockHttpServletRequestBuilder request, MockHttpSession session, String body, int status) throws Exception {
        return mvc.perform(request.session(session).with(csrf()).contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().is(status)).andReturn();
    }
    String createStudentBody(String code) {
        var c = catalog();
        return """
                {"fullName":"API Student","dateOfBirth":"2006-01-01",
                 "gender":"OTHER","majorId":%d,"classId":%d}
                """.formatted(c.getMajor().getId(), c.getId());
    }
    String updateStudentBody(Student s, String name, StudentStatus status) {
        return """
                {"fullName":"%s","dateOfBirth":"2006-01-01","gender":"OTHER","citizenId":"%s",
                 "majorId":%d,"classId":%d,"trainingProgramId":%d,"status":"%s"}
                """.formatted(name, s.getCitizenId(), s.getMajor().getId(), s.getStudentClass().getId(),
                        s.getTrainingProgram().getId(), status);
    }

    @Test void realSessionLoginCsrfLogoutAndSafeAccountResponse() throws Exception {
        mvc.perform(get("/api/students")).andExpect(status().isUnauthorized());
        var csrfResult = mvc.perform(get("/api/auth/csrf")).andExpect(status().isOk()).andReturn();
        var session = (MockHttpSession) csrfResult.getRequest().getSession(false);
        var token = body(csrfResult);
        mvc.perform(post("/api/auth/login").session(session).param("username", "admin-test").param("password", PASSWORD))
                .andExpect(status().isForbidden());
        mvc.perform(post("/api/auth/login").session(session)
                .header(token.get("headerName").asText(), token.get("token").asText())
                .param("username", "admin-test").param("password", PASSWORD)).andExpect(status().isNoContent());
        mvc.perform(get("/api/auth/me").session(session)).andExpect(status().isOk())
                .andExpect(jsonPath("$.role").value("ADMIN")).andExpect(jsonPath("$.passwordHash").doesNotExist())
                .andExpect(jsonPath("$.activationTokenHash").doesNotExist());
        var refreshed = body(mvc.perform(get("/api/auth/csrf").session(session)).andExpect(status().isOk()).andReturn());
        mvc.perform(post("/api/auth/logout").session(session)
                .header(refreshed.get("headerName").asText(), refreshed.get("token").asText()))
                .andExpect(status().isNoContent());
        assertThat(session.isInvalid()).isTrue();
    }

    @Test void rejectsWrongPasswordAndUnactivatedAccounts() throws Exception {
        var user = account("pending", UserRole.STAFF); user.setPasswordSetupRequired(true); users.flush();
        mvc.perform(post("/api/auth/login").with(csrf()).param("username", "admin-test").param("password", "wrong"))
                .andExpect(status().isUnauthorized());
        mvc.perform(post("/api/auth/login").with(csrf()).param("username", "pending").param("password", PASSWORD))
                .andExpect(status().isUnauthorized());
    }

    @Test void createsActivatesAndReadsStudentWithoutCredentialLeaks() throws Exception {
        var adminSession = login("admin-test");
        var created = body(send(post("/api/students"), adminSession, createStudentBody("API001"), 201));
        long id = created.get("student").get("id").asLong();
        String activation = json.writeValueAsString(java.util.Map.of("token", created.get("activationToken").asText(), "password", PASSWORD));
        mvc.perform(post("/api/auth/activate").with(csrf()).contentType(MediaType.APPLICATION_JSON).content(activation))
                .andExpect(status().isNoContent());
        var studentSession = login(created.get("student").get("studentCode").asText());
        mvc.perform(get("/api/me/profile").session(studentSession)).andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(id)).andExpect(jsonPath("$.passwordHash").doesNotExist())
                .andExpect(jsonPath("$.activationToken").doesNotExist());
        mvc.perform(post("/api/auth/activate").with(csrf()).contentType(MediaType.APPLICATION_JSON).content(activation))
                .andExpect(status().isBadRequest());
        mvc.perform(get("/api/students").session(adminSession).param("search", created.get("student").get("studentCode").asText()))
                .andExpect(status().isOk()).andExpect(jsonPath("$.totalElements").value(1));
    }

    @Test void restrictsStudentAndStaffAdministrativeAccess() throws Exception {
        var s = student("SELF");
        var studentSession = login("SELF");
        mvc.perform(get("/api/students").session(studentSession)).andExpect(status().isForbidden());
        mvc.perform(get("/api/users").session(studentSession)).andExpect(status().isForbidden());
        mvc.perform(get("/api/access-logs").session(studentSession)).andExpect(status().isForbidden());
        send(post("/api/majors"), studentSession, "{\"facultyId\":" + faculty.getId() + ",\"shortCode\":\"BAD\",\"name\":\"Bad\",\"active\":true}", 403);
        mvc.perform(get("/api/students/" + s.getId() + "/addresses").session(studentSession)).andExpect(status().isForbidden());
        var staff = login("staff-test");
        mvc.perform(get("/api/students").session(staff)).andExpect(status().isOk());
        mvc.perform(get("/api/users").session(staff)).andExpect(status().isForbidden());
        mvc.perform(get("/api/access-logs").session(staff)).andExpect(status().isForbidden());
    }

    @Test void isolatesNestedRecordsBetweenStudents() throws Exception {
        student("ONE"); student("TWO");
        var one = login("ONE"); var two = login("TWO");
        String contact = "{\"fullName\":\"Emergency\",\"phoneNumber\":\"0900000001\",\"priority\":1}";
        long id = body(send(post("/api/me/emergency-contacts"), one, contact, 201)).get("id").asLong();
        mvc.perform(get("/api/me/emergency-contacts/" + id).session(two)).andExpect(status().isNotFound());
        send(put("/api/me/emergency-contacts/" + id), two, contact, 404);
        mvc.perform(delete("/api/me/emergency-contacts/" + id).session(two).with(csrf())).andExpect(status().isNotFound());
        assertThat(contacts.existsById(id)).isTrue();
    }

    @Test void catalogCrudChecksUniquenessReferencesAndDeletion() throws Exception {
        var session = login("admin-test");
        long majorId = body(send(post("/api/majors"), session,
                "{\"facultyId\":" + faculty.getId() + ",\"shortCode\":\"NEW\",\"name\":\"New major\",\"description\":\"Description\",\"active\":true}", 201)).get("id").asLong();
        send(put("/api/majors/" + majorId), session,
                "{\"facultyId\":" + faculty.getId() + ",\"shortCode\":\"NEW\",\"name\":\"Renamed\",\"active\":true}", 200);
        send(post("/api/majors"), session, "{\"facultyId\":" + faculty.getId() + ",\"shortCode\":\"NEW\",\"name\":\"Duplicate\",\"active\":true}", 409);
        String program = "{\"cohort\":2024,\"degreeType\":\"ENGINEER\",\"name\":\"New program\",\"majorId\":" + majorId + ",\"active\":true}";
        long programId = body(send(post("/api/training-programs"), session, program, 201)).get("id").asLong();
        String group = "{\"majorId\":" + majorId + ",\"programId\":" + programId + ",\"active\":true}";
        long classId = body(send(post("/api/classes"), session, group, 201)).get("id").asLong();
        mvc.perform(delete("/api/majors/" + majorId).session(session).with(csrf())).andExpect(status().isConflict());
        mvc.perform(delete("/api/training-programs/" + programId).session(session).with(csrf())).andExpect(status().isConflict());
        mvc.perform(delete("/api/classes/" + classId).session(session).with(csrf())).andExpect(status().isNoContent());
        mvc.perform(delete("/api/training-programs/" + programId).session(session).with(csrf())).andExpect(status().isNoContent());
        mvc.perform(delete("/api/majors/" + majorId).session(session).with(csrf())).andExpect(status().isNoContent());
        mvc.perform(get("/api/majors/" + majorId).session(session)).andExpect(status().isNotFound());
    }

    @Test void rejectsIncompatibleClassAndMovingCatalogsInUse() throws Exception {
        var s = student("LINKED"); var session = login("admin-test");
        long other = body(send(post("/api/majors"), session,
                "{\"facultyId\":" + faculty.getId() + ",\"shortCode\":\"OTHER\",\"name\":\"Other major\",\"active\":true}", 201)).get("id").asLong();
        String wrongClass = "{\"majorId\":" + other + ",\"programId\":" + s.getTrainingProgram().getId() + ",\"active\":true}";
        send(post("/api/classes"), session, wrongClass, 400);
        String move = "{\"cohort\":2024,\"degreeType\":\"ENGINEER\",\"name\":\"Program\",\"majorId\":" + other + ",\"active\":true}";
        send(put("/api/training-programs/" + s.getTrainingProgram().getId()), session, move, 409);
        var otherProgram = body(send(post("/api/training-programs"), session,
                json.writeValueAsString(java.util.Map.of("cohort", 2024, "degreeType", "ENGINEER", "name", "Other program", "majorId", other, "active", true)), 201));
        String moveClass = json.writeValueAsString(java.util.Map.of( "programId", otherProgram.get("id").asLong(), "active", true));
        send(put("/api/classes/" + s.getStudentClass().getId()), session, moveClass, 409);
    }

    @Test void validatesRequestsPaginationAndCsrf() throws Exception {
        var session = login("admin-test");
        send(post("/api/majors"), session, "{\"facultyId\":" + faculty.getId() + ",\"shortCode\":\" \",\"name\":\"Invalid\",\"active\":true}", 400);
        send(post("/api/majors"), session, "{\"facultyId\":" + faculty.getId() + ",\"shortCode\":\"BAD\",\"name\":\"Invalid\"}", 400);
        send(post("/api/majors"), session, "{\"facultyId\":" + faculty.getId() + ",\"shortCode\":\"BAD\",\"name\":\"Invalid\",\"active\":true,\"role\":\"ADMIN\"}", 400);
        mvc.perform(get("/api/students").session(session).param("size", "101")).andExpect(status().isBadRequest());
        mvc.perform(get("/api/students").session(session).param("page", "-1")).andExpect(status().isBadRequest());
        mvc.perform(get("/api/students/no-id").session(session)).andExpect(status().isBadRequest());
        mvc.perform(post("/api/majors").session(session).contentType(MediaType.APPLICATION_JSON)
                .content("{\"shortCode\":\"CSRF\",\"name\":\"Rejected\",\"active\":true}"))
                .andExpect(status().isForbidden());
    }

    @Test void refreshesCompletionWhenRelatedDataIsCreatedUpdatedAndDeleted() throws Exception {
        var student = student("COMPLETE"); var session = login("COMPLETE");
        send(put("/api/me/profile"), session, """
                {"placeOfBirth":"City","ethnicity":"Test","nationality":"Test","citizenIdIssueDate":"2022-01-01",
                 "healthInsuranceNumber":"TEST","healthInsuranceExpiry":"2030-01-01","personalEmail":"test@example.invalid",
                 "phoneNumber":"0900000000","freeHealthInsurance":false}
                """, 200);
        for (String type : new String[]{"CURRENT", "PERMANENT"})
            send(post("/api/me/addresses"), session, """
                    {"addressType":"%s","addressLine":"Street","provinceCity":"City","wardCommune":"Ward","current":true}
                    """.formatted(type), 201);
        for (String role : new String[]{"MOTHER", "FATHER"})
            send(post("/api/me/family-members"), session, """
                    {"relationship":"%s","unavailable":true,"hasCollegeDegree":false}
                    """.formatted(role), 201);
        var contact = body(send(post("/api/me/emergency-contacts"), session,
                "{\"fullName\":\"Contact\",\"phoneNumber\":\"0900000001\",\"priority\":1}", 201));
        assertThat(students.findById(student.getId()).orElseThrow().getProfileStatus()).isEqualTo(ProfileStatus.COMPLETE);
        mvc.perform(get("/api/me/completion").session(session)).andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("COMPLETE"));
        mvc.perform(delete("/api/me/emergency-contacts/" + contact.get("id").asLong()).session(session).with(csrf()))
                .andExpect(status().isNoContent());
        assertThat(students.findById(student.getId()).orElseThrow().getProfileStatus()).isEqualTo(ProfileStatus.INCOMPLETE);
        assertThat(students.findById(student.getId()).orElseThrow().getProfileCompletedAt()).isNull();
    }

    @Test void supportsEditingAndDeletingEveryContactSection() throws Exception {
        student("EDIT"); var session = login("EDIT");
        String[][] records = {
            {"addresses", "{\"addressType\":\"CURRENT\",\"current\":true,\"addressLine\":\"A\"}",
                "{\"addressType\":\"CURRENT\",\"current\":false,\"addressLine\":\"B\"}", "addressLine", "B"},
            {"family-members", "{\"relationship\":\"GUARDIAN\",\"fullName\":\"A\",\"hasCollegeDegree\":false,\"unavailable\":false}",
                "{\"relationship\":\"GUARDIAN\",\"fullName\":\"B\",\"hasCollegeDegree\":true,\"unavailable\":false}", "fullName", "B"},
            {"emergency-contacts", "{\"fullName\":\"A\",\"phoneNumber\":\"0900000000\",\"priority\":1}",
                "{\"fullName\":\"B\",\"phoneNumber\":\"0900000001\",\"priority\":2}", "fullName", "B"},
            {"post-graduation-contacts", "{\"email\":\"a@example.invalid\"}",
                "{\"email\":\"b@example.invalid\"}", "email", "b@example.invalid"}
        };
        for (var record : records) {
            String base = "/api/me/" + record[0];
            long id = body(send(post(base), session, record[1], 201)).get("id").asLong();
            send(put(base + "/" + id), session, record[2], 200);
            mvc.perform(get(base + "/" + id).session(session)).andExpect(status().isOk())
                    .andExpect(jsonPath("$." + record[3]).value(record[4]));
            mvc.perform(delete(base + "/" + id).session(session).with(csrf())).andExpect(status().isNoContent());
            mvc.perform(get(base).session(session)).andExpect(status().isOk()).andExpect(jsonPath("$.length()").value(0));
        }
    }

    @Test void archivesStudentPreservesRelationsAndRevokesExistingSession() throws Exception {
        var s = student("ARCHIVE"); var self = login("ARCHIVE"); var adminSession = login("admin-test");
        send(post("/api/me/emergency-contacts"), self, "{\"fullName\":\"Contact\",\"phoneNumber\":\"0900000000\",\"priority\":1}", 201);
        send(put("/api/students/" + s.getId()), adminSession, updateStudentBody(s, "Updated Name", StudentStatus.ACTIVE), 200);
        mvc.perform(delete("/api/students/" + s.getId()).session(adminSession).with(csrf())).andExpect(status().isNoContent());
        assertThat(students.findById(s.getId()).orElseThrow().getStatus()).isEqualTo(StudentStatus.INACTIVE);
        assertThat(contacts.findByStudentId(s.getId())).hasSize(1);
        mvc.perform(get("/api/me/profile").session(self)).andExpect(status().isUnauthorized());
        mvc.perform(post("/api/auth/login").with(csrf()).param("username", "ARCHIVE").param("password", PASSWORD))
                .andExpect(status().isUnauthorized());
    }

    @Test void preventsMassAssignmentAndInvalidEmergencyContacts() throws Exception {
        student("PROTECTED"); var session = login("PROTECTED");
        send(put("/api/me/profile"), session, "{\"fullName\":\"Tampered\",\"role\":\"ADMIN\"}", 400);
        send(post("/api/me/emergency-contacts"), session,
                "{\"fullName\":\"A\",\"phoneNumber\":\"0900000000\",\"priority\":0}", 400);
        send(post("/api/me/family-members"), session,
                "{\"relationship\":\"INVALID\",\"hasCollegeDegree\":false,\"unavailable\":false}", 400);
        send(post("/api/me/post-graduation-contacts"), session, "{\"email\":\"not-an-email\"}", 400);
    }

    @Test void administersStaffAccountsAndImmediatelyRevokesDisabledSessions() throws Exception {
        var session = login("admin-test"); var staffSession = login("staff-test");
        var staff = users.findByUsername("staff-test").orElseThrow();
        send(patch("/api/users/" + staff.getId() + "/enabled"), session, "{\"enabled\":false}", 200);
        mvc.perform(get("/api/students").session(staffSession)).andExpect(status().isUnauthorized());
        send(patch("/api/users/" + admin.getId() + "/enabled"), session, "{\"enabled\":false}", 409);
        var created = body(send(post("/api/users"), session, "{\"username\":\"new-staff\",\"role\":\"STAFF\"}", 201));
        assertThat(created.get("activationToken").asText()).isNotBlank();
        assertThat(created.get("user").has("passwordHash")).isFalse();
        send(post("/api/users"), session, "{\"username\":\"wrong-student\",\"role\":\"STUDENT\"}", 400);
    }

    @Test void reissuesExpiredActivationAndInvalidatesThePreviousToken() throws Exception {
        var session = login("admin-test");
        String request = json.writeValueAsString(java.util.Map.of("username", "activate-again", "role", "STAFF"));
        var created = body(send(post("/api/users"), session, request, 201));
        long id = created.get("user").get("id").asLong();
        users.findById(id).orElseThrow().setActivationExpiresAt(java.time.LocalDateTime.now().minusDays(1));
        var renewed = body(mvc.perform(post("/api/users/" + id + "/activation-token").session(session).with(csrf()))
                .andExpect(status().isOk()).andReturn());
        assertThat(renewed.get("activationToken").asText()).isNotEqualTo(created.get("activationToken").asText());
        String oldToken = json.writeValueAsString(java.util.Map.of("token", created.get("activationToken").asText(), "password", PASSWORD));
        mvc.perform(post("/api/auth/activate").with(csrf()).contentType(MediaType.APPLICATION_JSON).content(oldToken))
                .andExpect(status().isBadRequest());
        String newToken = json.writeValueAsString(java.util.Map.of("token", renewed.get("activationToken").asText(), "password", PASSWORD));
        mvc.perform(post("/api/auth/activate").with(csrf()).contentType(MediaType.APPLICATION_JSON).content(newToken))
                .andExpect(status().isNoContent());
        login("activate-again");
        mvc.perform(post("/api/users/" + id + "/activation-token").session(session).with(csrf()))
                .andExpect(status().isConflict());
    }

    String jsonBody(Object... pairs) {
        var values = new java.util.LinkedHashMap<String, Object>();
        for (int i = 0; i < pairs.length; i += 2) values.put((String) pairs[i], pairs[i + 1]);
        return json.writeValueAsString(values);
    }

    @Test void createsHierarchyWithOnlyImmediateParentIds() throws Exception {
        var session = login("admin-test");
        long majorId = body(send(post("/api/majors"), session,
                jsonBody("facultyId", faculty.getId(), "shortCode", "CHAIN", "name", "Chain major", "active", true), 201)).get("id").asLong();
        for (int i = 1; i <= 2; i++) {
            long programId = body(send(post("/api/training-programs"), session,
                    jsonBody("degreeType", "ENGINEER", "cohort", 2024 + i, "name", "Program " + i, "majorId", majorId, "active", true), 201))
                    .get("id").asLong();
            for (int j = 1; j <= 2; j++) {
                var group = body(send(post("/api/classes"), session,
                        jsonBody("programId", programId, "active", true), 201));
                long classId = group.get("id").asLong();
                assertThat(group.get("majorId").asLong()).isEqualTo(majorId);
                var created = body(send(post("/api/students"), session,
                        jsonBody("fullName", "Chain student", "classId", classId), 201));
                long studentId = created.get("student").get("id").asLong();
                mvc.perform(get("/api/students/" + studentId).session(session))
                        .andExpect(status().isOk()).andExpect(jsonPath("$.majorId").value(majorId))
                        .andExpect(jsonPath("$.classId").value(classId))
                        .andExpect(jsonPath("$.trainingProgramId").value(programId));
            }
        }
    }

    @Test void rejectsMissingAndUnknownParentsBeforeCreatingAccounts() throws Exception {
        var session = login("admin-test");
        long before = users.count();
        send(post("/api/training-programs"), session, jsonBody("degreeType", "ENGINEER", "cohort", 2024, "name", "Program", "active", true), 400);
        send(post("/api/training-programs"), session,
                jsonBody("degreeType", "ENGINEER", "cohort", 2024, "name", "Program", "majorId", 999999L, "active", true), 404);
        send(post("/api/classes"), session, jsonBody("active", true), 400);
        send(post("/api/classes"), session, jsonBody("programId", 999999L, "active", true), 404);
        send(post("/api/students"), session, jsonBody("fullName", "Student"), 400);
        send(post("/api/students"), session,
                jsonBody("fullName", "Student", "classId", 999999L), 404);
        assertThat(users.count()).isEqualTo(before);
        assertThat(students.count()).isZero();
    }

    @Test void rejectsConflictingStudentIdsEvenForProgramsInTheSameMajor() throws Exception {
        var c = catalog(); var session = login("admin-test");
        long otherProgram = body(send(post("/api/training-programs"), session,
                jsonBody("degreeType", "ENGINEER", "cohort", 2024, "name", "Other program", "majorId", c.getMajor().getId(), "active", true), 201))
                .get("id").asLong();
        long before = users.count();
        send(post("/api/students"), session,
                jsonBody("fullName", "Student", "classId", c.getId(), "trainingProgramId", otherProgram), 400);
        send(post("/api/students"), session,
                jsonBody("fullName", "Student", "classId", c.getId(), "majorId", 999999L), 400);
        assertThat(users.count()).isEqualTo(before);
        var s = student("EDIT_LINK");
        send(put("/api/students/" + s.getId()), session,
                jsonBody("fullName", "Student", "classId", c.getId(), "trainingProgramId", otherProgram, "status", "ACTIVE"), 400);
        assertThat(s.getTrainingProgram().getId()).isEqualTo(c.getProgram().getId());
        send(put("/api/classes/" + c.getId()), session,
                jsonBody("programId", otherProgram, "active", true), 409);
    }

    @Test void conflictingLegacyEmailRejectsOnboardingWithoutCreatingAccount() throws Exception {
        var existing = student("LEGACYMAIL");
        existing.getStudentClass().setCohort(2199);
        existing.setSchoolEmail("stu2199000001@sv.pbl4.edu.vn");
        students.flush();
        long userCount = users.count(), studentCount = students.count();
        var session = login("admin-test");
        send(post("/api/students"), session,
                jsonBody("fullName", "New Student", "classId", existing.getStudentClass().getId()), 409);
        assertThat(users.count()).isEqualTo(userCount);
        assertThat(students.count()).isEqualTo(studentCount);
    }

    @Test void schoolEmailIsGeneratedReturnedAndCannotBeSuppliedByClients() throws Exception {
        var c = catalog(); var session = login("admin-test");
        var created = body(send(post("/api/students"), session,
                jsonBody("fullName", "Same Name", "classId", c.getId()), 201)).get("student");
        String code = created.get("studentCode").asString();
        String email = code.replace("-", "").toLowerCase(java.util.Locale.ROOT) + "@sv.pbl4.edu.vn";
        assertThat(created.get("schoolEmail").asString()).isEqualTo(email);
        long id = created.get("id").asLong();
        var second = body(send(post("/api/students"), session,
                jsonBody("fullName", "Same Name", "classId", c.getId()), 201)).get("student");
        assertThat(second.get("schoolEmail").asString()).isNotEqualTo(email);
        send(post("/api/students"), session,
                jsonBody("fullName", "Injected", "classId", c.getId(), "schoolEmail", "manual@example.com"), 400);
        send(put("/api/students/" + id), session,
                jsonBody("fullName", "Renamed", "classId", c.getId(), "status", "ACTIVE", "schoolEmail", "manual@example.com"), 400);
        send(put("/api/students/" + id), session,
                jsonBody("fullName", "Renamed", "classId", c.getId(), "status", "ACTIVE", "studentCode", "OTHER"), 400);
        var updated = body(send(put("/api/students/" + id), session,
                jsonBody("fullName", "Renamed", "classId", c.getId(), "status", "ACTIVE", "secondaryProgramId", c.getProgram().getId()), 200));
        assertThat(updated.get("schoolEmail").asString()).isEqualTo(email);
        assertThat(updated.get("studentCode").asString()).isEqualTo(code);
        mvc.perform(get("/api/students/" + id).session(session)).andExpect(status().isOk())
                .andExpect(jsonPath("$.schoolEmail").value(email));
    }

    @Test void transferringStudentDerivesBothMajorAndProgramAndPutCannotClearThem() throws Exception {
        var s = student("TRANSFER"); var session = login("admin-test");
        long major = body(send(post("/api/majors"), session,
                jsonBody("facultyId", faculty.getId(), "shortCode", "DEST", "name", "Destination", "active", true), 201)).get("id").asLong();
        long program = body(send(post("/api/training-programs"), session,
                jsonBody("degreeType", "ENGINEER", "cohort", 2024, "name", "Destination program", "majorId", major, "active", true), 201)).get("id").asLong();
        long group = body(send(post("/api/classes"), session,
                jsonBody("programId", program, "active", true), 201)).get("id").asLong();
        var updated = body(send(put("/api/students/" + s.getId()), session,
                jsonBody("fullName", "Transferred", "classId", group, "status", "ACTIVE"), 200));
        assertThat(updated.get("studentCode").asString()).isEqualTo("TRANSFER");
        assertThat(updated.get("schoolEmail").asString()).isEqualTo("transfer@sv.pbl4.edu.vn");
        assertThat(updated.get("majorId").asLong()).isEqualTo(major);
        assertThat(updated.get("trainingProgramId").asLong()).isEqualTo(program);
        var repeated = body(send(put("/api/students/" + s.getId()), session,
                jsonBody("fullName", "Transferred", "classId", group, "majorId", null, "trainingProgramId", null, "status", "ACTIVE"), 200));
        assertThat(repeated.get("trainingProgramId").asLong()).isEqualTo(program);
        assertThat(repeated.get("majorId").asLong()).isEqualTo(major);
    }

    @Test void rejectsNewStudentsForAnyInactiveParentButAllowsExistingProfileEdits() throws Exception {
        var s = student("EXISTING"); var c = s.getStudentClass(); var session = login("admin-test");
        String request = jsonBody("fullName", "Student", "classId", c.getId());
        c.setActive(false);
        send(post("/api/students"), session, request, 400);
        c.setActive(true); c.getProgram().setActive(false);
        send(post("/api/students"), session, request, 400);
        c.getProgram().setActive(true); c.getMajor().setActive(false);
        send(post("/api/students"), session, request, 400);
        send(put("/api/students/" + s.getId()), session,
                jsonBody("fullName", "Edited", "classId", c.getId(), "status", "ACTIVE"), 200);
        assertThat(users.existsByUsername("NEW_STUDENT")).isFalse();
    }

    @Test void unusedClassCanMoveProgramsAndItsMajorIsDerived() throws Exception {
        var c = catalog(); var session = login("admin-test");
        long major = body(send(post("/api/majors"), session,
                jsonBody("facultyId", faculty.getId(), "shortCode", "NEWPARENT", "name", "New parent", "active", true), 201)).get("id").asLong();
        long program = body(send(post("/api/training-programs"), session,
                jsonBody("degreeType", "ENGINEER", "cohort", 2024, "name", "Program", "majorId", major, "active", true), 201)).get("id").asLong();
        var updated = body(send(put("/api/classes/" + c.getId()), session,
                jsonBody("programId", program, "active", true), 200));
        assertThat(updated.get("majorId").asLong()).isEqualTo(major);
        assertThat(updated.get("programId").asLong()).isEqualTo(program);
    }

    @Test void facultyCrudAndAuthorization() throws Exception {
        var session = login("staff-test");
        String payload = jsonBody("shortCode", "FNEW", "name", "New faculty", "description", "Description", "active", true);
        long id = body(send(post("/api/faculties"), session, payload, 201)).get("id").asLong();
        send(post("/api/faculties"), session, payload, 409);
        send(put("/api/faculties/" + id), session,
                jsonBody("shortCode", "FNEW", "name", "Updated faculty", "active", true), 200);
        mvc.perform(get("/api/faculties/" + id).session(session)).andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("Updated faculty"));
        student("FAC_READER"); var self = login("FAC_READER");
        mvc.perform(get("/api/faculties").session(self)).andExpect(status().isOk());
        send(post("/api/faculties"), self, payload, 403);
        send(put("/api/faculties/" + id), self, payload, 403);
        mvc.perform(delete("/api/faculties/" + id).session(self).with(csrf())).andExpect(status().isForbidden());
        mvc.perform(delete("/api/faculties/" + id).session(session).with(csrf())).andExpect(status().isNoContent());
        mvc.perform(get("/api/faculties/" + id).session(session)).andExpect(status().isNotFound());
    }

    @Test void majorsRequireExistingFacultyAndFacultyCanHaveSeveralMajors() throws Exception {
        var session = login("admin-test");
        send(post("/api/majors"), session, jsonBody("shortCode", "MISSINGF", "name", "Missing", "active", true), 400);
        send(post("/api/majors"), session,
                jsonBody("shortCode", "UNKNOWNF", "name", "Unknown", "facultyId", 999999L, "active", true), 404);
        for (int i = 0; i < 2; i++) {
            var major = body(send(post("/api/majors"), session,
                    jsonBody("shortCode", "MULTI" + i, "name", "Major " + i, "facultyId", faculty.getId(), "active", true), 201));
            assertThat(major.get("facultyId").asLong()).isEqualTo(faculty.getId());
        }
        mvc.perform(delete("/api/faculties/" + faculty.getId()).session(session).with(csrf())).andExpect(status().isConflict());
        var c = catalog();
        long other = body(send(post("/api/faculties"), session,
                jsonBody("shortCode", "OTHERF", "name", "Other faculty", "active", true), 201)).get("id").asLong();
        send(put("/api/majors/" + c.getMajor().getId()), session,
                jsonBody("shortCode", "CS", "name", "Computer science", "facultyId", other, "active", true), 409);
    }

    @Test void inactiveFacultyBlocksNewAcademicAssignments() throws Exception {
        var c = catalog(); var session = login("admin-test");
        faculty.setActive(false); faculties.flush();
        send(post("/api/majors"), session,
                jsonBody("shortCode", "BLOCKED", "name", "Major", "facultyId", faculty.getId(), "active", true), 400);
        send(post("/api/training-programs"), session,
                jsonBody("degreeType", "ENGINEER", "cohort", 2024, "name", "Program", "majorId", c.getMajor().getId(), "active", true), 400);
        send(post("/api/classes"), session,
                jsonBody("programId", c.getProgram().getId(), "active", true), 400);
        send(post("/api/students"), session,
                jsonBody("fullName", "Student", "classId", c.getId()), 400);
        assertThat(users.existsByUsername("BLOCKED")).isFalse();
    }

    @Test void persistsDegreeEnumAndAllCreditFieldsAndAllowsReplacingThem() throws Exception {
        var c = catalog(); var session = login("admin-test");
        for (String degree : new String[]{"BACHELOR", "ENGINEER", "MASTER"}) {
            var program = body(send(post("/api/training-programs"), session,
                    jsonBody("cohort", 2020 + com.pbl4.studentweb.trainingprogram.entity.DegreeType.valueOf(degree).ordinal(), "name", "Degree program", "majorId", c.getMajor().getId(),
                            "degreeType", degree, "numberOfSemesters", 8, "totalCredits", 140,
                            "requiredCredits", 110, "electiveCredits", 30, "active", true), 201));
            long id = program.get("id").asLong();
            assertThat(program.get("degreeType").asText()).isEqualTo(degree);
            assertThat(program.get("numberOfSemesters").asInt()).isEqualTo(8);
            assertThat(program.get("totalCredits").asInt()).isEqualTo(140);
            assertThat(program.get("requiredCredits").asInt()).isEqualTo(110);
            assertThat(program.get("electiveCredits").asInt()).isEqualTo(30);
            assertThat(programs.findById(id).orElseThrow().getDegreeType().name()).isEqualTo(degree);
            mvc.perform(get("/api/training-programs/" + id).session(session)).andExpect(status().isOk())
                    .andExpect(jsonPath("$.degreeType").value(degree));
            var updated = body(send(put("/api/training-programs/" + id), session,
                    jsonBody("cohort", 2020 + com.pbl4.studentweb.trainingprogram.entity.DegreeType.valueOf(degree).ordinal(), "name", "Updated", "majorId", c.getMajor().getId(),
                            "degreeType", "MASTER", "numberOfSemesters", 4, "totalCredits", 60,
                            "requiredCredits", 45, "electiveCredits", 15, "active", true), 200));
            assertThat(updated.get("numberOfSemesters").asInt()).isEqualTo(4);
            assertThat(updated.get("totalCredits").asInt()).isEqualTo(60);
        }
    }

    @Test void rejectsInvalidDegreesSemestersAndCreditTotals() throws Exception {
        var c = catalog(); var session = login("admin-test");
        var payload = new java.util.LinkedHashMap<String, Object>();
        payload.put("cohort", 2024); payload.put("degreeType", "ENGINEER"); payload.put("name", "Program");
        payload.put("majorId", c.getMajor().getId()); payload.put("active", true);
        for (var entry : java.util.Map.<String, Object>of("degreeType", "DOCTOR", "numberOfSemesters", 0,
                "totalCredits", -1, "requiredCredits", -1, "electiveCredits", -1).entrySet()) {
            payload.put(entry.getKey(), entry.getValue());
            send(post("/api/training-programs"), session, json.writeValueAsString(payload), 400);
            send(put("/api/training-programs/" + c.getProgram().getId()), session, json.writeValueAsString(payload), 400);
            payload.remove(entry.getKey());
            payload.put("degreeType", "ENGINEER");
        }
        payload.put("totalCredits", 100); payload.put("requiredCredits", 110);
        send(post("/api/training-programs"), session, json.writeValueAsString(payload), 400);
        payload.put("requiredCredits", 80); payload.put("electiveCredits", 30);
        send(post("/api/training-programs"), session, json.writeValueAsString(payload), 400);
        payload.put("electiveCredits", 10);
        send(post("/api/training-programs"), session, json.writeValueAsString(payload), 400);
        payload.put("requiredCredits", 100); payload.put("electiveCredits", 0);
        send(post("/api/training-programs"), session, json.writeValueAsString(payload), 201);
    }
    @Test void acceptsZeroCreditsAndRejectsInvalidSumOnUpdate() throws Exception {
        var c = catalog(); var session = login("admin-test");
        var created = body(send(post("/api/training-programs"), session,
                jsonBody("degreeType", "ENGINEER", "cohort", 2024, "name", "Program", "majorId", c.getMajor().getId(),
                        "numberOfSemesters", 1, "totalCredits", 0, "requiredCredits", 0,
                        "electiveCredits", 0, "active", true), 201));
        send(put("/api/training-programs/" + created.get("id").asLong()), session,
                jsonBody("degreeType", "ENGINEER", "cohort", 2024, "name", "Program", "majorId", c.getMajor().getId(),
                        "totalCredits", 100, "requiredCredits", 60, "electiveCredits", 30, "active", true), 400);
        send(put("/api/training-programs/" + created.get("id").asLong()), session,
                jsonBody("degreeType", "ENGINEER", "cohort", 2024, "name", "Program", "majorId", c.getMajor().getId(),
                        "totalCredits", Integer.MAX_VALUE, "requiredCredits", Integer.MAX_VALUE,
                        "electiveCredits", Integer.MAX_VALUE, "active", true), 400);
    }

    @Test void programVariantsCoexistAndRoundTripWithoutAllowingDuplicateCodes() throws Exception {
        var c = catalog(); var session = login("admin-test");
        long majorId = c.getMajor().getId();
        var regular = body(send(post("/api/training-programs"), session,
                jsonBody("name", "Regular", "majorId", majorId, "cohort", 2020,
                        "degreeType", "ENGINEER", "active", true), 201));
        var clc = body(send(post("/api/training-programs"), session,
                jsonBody("name", "CLC", "majorId", majorId, "cohort", 2020,
                        "degreeType", "ENGINEER", "variantCode", " clc ", "active", true), 201));
        assertThat(regular.get("code").asString()).isEqualTo("PRG-CS-2020-ENG");
        assertThat(clc.get("code").asString()).isEqualTo("PRG-CS-2020-ENG-CLC");
        long id = clc.get("id").asLong();
        mvc.perform(get("/api/training-programs/" + id).session(session))
                .andExpect(status().isOk()).andExpect(jsonPath("$.variantCode").value("CLC"));
        send(post("/api/training-programs"), session,
                jsonBody("name", "Duplicate", "majorId", majorId, "cohort", 2020,
                        "degreeType", "ENGINEER", "variantCode", "CLC", "active", true), 409);
        send(put("/api/training-programs/" + id), session,
                jsonBody("name", "Edited CLC", "majorId", majorId, "cohort", 2020,
                        "degreeType", "ENGINEER", "variantCode", "CLC", "active", true), 200);
        send(put("/api/training-programs/" + id), session,
                jsonBody("name", "Collision", "majorId", majorId, "cohort", 2020,
                        "degreeType", "ENGINEER", "active", true), 409);
        for (String invalid : new String[]{"TOOLONG", "1CLC", "CLC-EN", "ĐT"})
            send(post("/api/training-programs"), session,
                    jsonBody("name", "Invalid", "majorId", majorId, "cohort", 2020,
                            "degreeType", "ENGINEER", "variantCode", invalid, "active", true), 400);
    }

    @Test void catalogCodesRemainUniqueOnCreateAndUpdate() throws Exception {
        var c = catalog(); var session = login("admin-test");
        for (String endpoint : new String[]{"majors", "training-programs"}) {
            String url = "/api/" + endpoint;
            String firstPayload = endpoint.equals("majors")
                    ? jsonBody("shortCode", " qa ", "name", "A", "facultyId", faculty.getId(), "active", true)
                    : jsonBody("name", "A", "majorId", c.getMajor().getId(), "cohort", 2024, "degreeType", "ENGINEER", "active", true);
            String secondPayload = endpoint.equals("majors")
                    ? jsonBody("shortCode", "QB", "name", "B", "facultyId", faculty.getId(), "active", true)
                    : jsonBody("name", "B", "majorId", c.getMajor().getId(), "cohort", 2025, "degreeType", "ENGINEER", "active", true);
            var first = body(send(post(url), session, firstPayload, 201));
            var second = body(send(post(url), session, secondPayload, 201));
            send(post(url), session, firstPayload, 409);
            send(put(url + "/" + second.get("id").asLong()), session, firstPayload, 409);
            send(put(url + "/" + first.get("id").asLong()), session, firstPayload, 200);
        }
    }

    @Test void generatedCodesAndForeignKeysAndStudentIdentity() throws Exception {
        var session = login("admin-test");
        var f = body(send(post("/api/faculties"), session,
                jsonBody("shortCode", " it ", "name", "IT", "active", true), 201));
        assertThat(f.get("code").asText()).isEqualTo("FAC-IT");
        var m = body(send(post("/api/majors"), session,
                jsonBody("shortCode", " it ", "name", "IT", "facultyId", f.get("id").asLong(), "active", true), 201));
        assertThat(m.get("code").asText()).isEqualTo("MAJ-IT");
        var p = body(send(post("/api/training-programs"), session,
                jsonBody("name", "Program", "majorId", m.get("id").asLong(), "cohort", 2041, "degreeType", "ENGINEER", "active", true), 201));
        assertThat(p.get("code").asText()).isEqualTo("PRG-IT-2041-ENG");
        var c = body(send(post("/api/classes"), session,
                jsonBody("programId", p.get("id").asLong(), "active", true), 201));
        assertThat(c.get("code").asText()).isEqualTo("CLS-IT-2041-01");
        var c2 = body(send(post("/api/classes"), session,
                jsonBody("programId", p.get("id").asLong(), "active", true), 201));
        assertThat(c2.get("code").asText()).isEqualTo("CLS-IT-2041-02");
        var created = body(send(post("/api/students"), session,
                jsonBody("fullName", "Student", "classId", c.get("id").asLong()), 201)).get("student");
        assertThat(created.get("studentCode").asText()).isEqualTo("STU-2041-000001");
        long studentId = created.get("id").asLong();
        var updated = body(send(put("/api/students/" + studentId), session,
                jsonBody("fullName", "Moved", "classId", c2.get("id").asLong(), "status", "ACTIVE"), 200));
        assertThat(updated.get("studentCode").asText()).isEqualTo(created.get("studentCode").asText());
        assertThat(students.findById(studentId).orElseThrow().getUser().getUsername()).isEqualTo("STU-2041-000001");
        send(post("/api/students"), session, jsonBody("studentCode", "CUSTOM", "fullName", "Student", "classId", c.get("id").asLong()), 400);
        send(post("/api/classes"), session, jsonBody("code", "CUSTOM", "programId", p.get("id").asLong(), "active", true), 400);
        send(post("/api/classes"), session, jsonBody("cohort", 2042, "programId", p.get("id").asLong(), "active", true), 400);
        send(post("/api/faculties"), session, jsonBody("shortCode", "FAC-IT", "name", "IT", "active", true), 400);
    }
}
