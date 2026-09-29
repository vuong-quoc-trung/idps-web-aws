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
        var major = new Major(); major.setMajorCode("CS"); major.setMajorName("Computer science"); majors.save(major);
        var program = new TrainingProgram(); program.setProgramCode("CS2026"); program.setProgramName("Program");
        program.setMajor(major); programs.save(program);
        studentClass = new StudentClass(); studentClass.setClassCode("CS26"); studentClass.setMajor(major);
        studentClass.setProgram(program); return classes.saveAndFlush(studentClass);
    }
    Student student(String code) {
        var group = catalog(); var student = new Student();
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
                {"studentCode":"%s","fullName":"API Student","dateOfBirth":"2006-01-01",
                 "gender":"OTHER","majorId":%d,"classId":%d}
                """.formatted(code, c.getMajor().getId(), c.getId());
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
        var studentSession = login("API001");
        mvc.perform(get("/api/me/profile").session(studentSession)).andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(id)).andExpect(jsonPath("$.passwordHash").doesNotExist())
                .andExpect(jsonPath("$.activationToken").doesNotExist());
        mvc.perform(post("/api/auth/activate").with(csrf()).contentType(MediaType.APPLICATION_JSON).content(activation))
                .andExpect(status().isBadRequest());
        mvc.perform(get("/api/students").session(adminSession).param("search", "api001"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.totalElements").value(1));
    }

    @Test void restrictsStudentAndStaffAdministrativeAccess() throws Exception {
        var s = student("SELF");
        var studentSession = login("SELF");
        mvc.perform(get("/api/students").session(studentSession)).andExpect(status().isForbidden());
        mvc.perform(get("/api/users").session(studentSession)).andExpect(status().isForbidden());
        mvc.perform(get("/api/access-logs").session(studentSession)).andExpect(status().isForbidden());
        send(post("/api/majors"), studentSession, "{\"code\":\"BAD\",\"name\":\"Bad\",\"active\":true}", 403);
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
                "{\"code\":\"NEW\",\"name\":\"New major\",\"description\":\"Description\",\"active\":true}", 201)).get("id").asLong();
        send(put("/api/majors/" + majorId), session,
                "{\"code\":\"NEW\",\"name\":\"Renamed\",\"active\":true}", 200);
        send(post("/api/majors"), session, "{\"code\":\"NEW\",\"name\":\"Duplicate\",\"active\":true}", 409);
        String program = "{\"code\":\"NEWP\",\"name\":\"New program\",\"majorId\":" + majorId + ",\"active\":true}";
        long programId = body(send(post("/api/training-programs"), session, program, 201)).get("id").asLong();
        String group = "{\"code\":\"NEWC\",\"majorId\":" + majorId + ",\"programId\":" + programId + ",\"active\":true}";
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
                "{\"code\":\"OTHER\",\"name\":\"Other major\",\"active\":true}", 201)).get("id").asLong();
        String wrongClass = "{\"code\":\"WRONG\",\"majorId\":" + other + ",\"programId\":" + s.getTrainingProgram().getId() + ",\"active\":true}";
        send(post("/api/classes"), session, wrongClass, 400);
        String move = "{\"code\":\"CS2026\",\"name\":\"Program\",\"majorId\":" + other + ",\"active\":true}";
        send(put("/api/training-programs/" + s.getTrainingProgram().getId()), session, move, 409);
        String moveClass = "{\"code\":\"CS26\",\"majorId\":" + other + ",\"active\":true}";
        send(put("/api/classes/" + s.getStudentClass().getId()), session, moveClass, 409);
    }

    @Test void validatesRequestsPaginationAndCsrf() throws Exception {
        var session = login("admin-test");
        send(post("/api/majors"), session, "{\"code\":\" \",\"name\":\"Invalid\",\"active\":true}", 400);
        send(post("/api/majors"), session, "{\"code\":\"BAD\",\"name\":\"Invalid\"}", 400);
        send(post("/api/majors"), session, "{\"code\":\"BAD\",\"name\":\"Invalid\",\"active\":true,\"role\":\"ADMIN\"}", 400);
        mvc.perform(get("/api/students").session(session).param("size", "101")).andExpect(status().isBadRequest());
        mvc.perform(get("/api/students").session(session).param("page", "-1")).andExpect(status().isBadRequest());
        mvc.perform(get("/api/students/no-id").session(session)).andExpect(status().isBadRequest());
        mvc.perform(post("/api/majors").session(session).contentType(MediaType.APPLICATION_JSON)
                .content("{\"code\":\"CSRF\",\"name\":\"Rejected\",\"active\":true}"))
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
}
