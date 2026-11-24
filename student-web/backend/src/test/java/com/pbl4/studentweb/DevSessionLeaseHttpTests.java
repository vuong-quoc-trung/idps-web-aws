package com.pbl4.studentweb;

import com.pbl4.studentweb.accesslog.service.AuditJsonlExporter;
import com.pbl4.studentweb.user.entity.*;
import com.pbl4.studentweb.user.repository.UserRepository;
import java.net.URI;
import java.net.http.*;
import java.nio.file.*;
import java.time.Instant;
import java.util.Comparator;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.*;
import tools.jackson.databind.json.JsonMapper;
import static org.junit.jupiter.api.Assertions.*;

@ActiveProfiles("ws-i5-development")
@SpringBootTest(webEnvironment=SpringBootTest.WebEnvironment.RANDOM_PORT, properties={
    "server.address=127.0.0.1","spring.datasource.url=jdbc:h2:mem:devlease;MODE=PostgreSQL",
    "spring.datasource.username=sa","spring.datasource.password=","spring.jpa.hibernate.ddl-auto=create-drop",
    "spring.jpa.properties.hibernate.default_schema=PUBLIC","app.bootstrap.enabled=false",
    "app.audit.file.enabled=true","app.audit.file.hmac-key=development-test-only-key-of-32-bytes",
    "app.dev.account-locks=true","logging.level.root=WARN"})
class DevSessionLeaseHttpTests {
    static Path root;
    @BeforeAll static void prepareDirectory() throws Exception { root=Files.createTempDirectory("ws-session-"); }
    @DynamicPropertySource static void props(DynamicPropertyRegistry r) {
        r.add("app.dev.session-lease-dir",root::toString);
        r.add("app.audit.file.path",()->root.resolve("audit.jsonl").toString());
    }
    @AfterAll static void cleanup() throws Exception {
        try(var files=Files.walk(root)){ for(var path:files.sorted(Comparator.reverseOrder()).toList()) Files.delete(path); }
    }
    @Autowired UserRepository users;
    @Autowired PasswordEncoder encoder;
    @Autowired AuditJsonlExporter exporter;
    @Autowired JsonMapper mapper;
    @LocalServerPort int port;
    final HttpClient client=HttpClient.newHttpClient();
    HttpRequest.Builder request(String path){return HttpRequest.newBuilder(URI.create("http://127.0.0.1:"+port+"/api/auth/"+path));}
    HttpResponse<String> send(HttpRequest.Builder request) throws Exception {
        return client.send(request.build(),HttpResponse.BodyHandlers.ofString());
    }
    String cookie(HttpResponse<?> response){
        return response.headers().allValues("Set-Cookie").stream().filter(s->s.startsWith("JSESSIONID="))
            .findFirst().orElseThrow().split(";",2)[0];
    }
    String login() throws Exception {
        return cookie(login("dev-lease",204));
    }
    HttpResponse<String> login(String username,int expected) throws Exception {
        var csrf=send(request("csrf"));
        var token=mapper.readTree(csrf.body());
        var response=send(request("login").header("Cookie",cookie(csrf)).header(token.get("headerName").asText(),token.get("token").asText())
            .header("Content-Type","application/x-www-form-urlencoded").POST(HttpRequest.BodyPublishers.ofString("username="+username+"&password=FixturePassword1234")));
        assertEquals(expected,response.statusCode());
        return response;
    }
    @Test void accountLockRejectsLoginAndOnlyAccessOfTheBoundActor() throws Exception {
        var target = fixture("account-target");
        fixture("account-control");
        String first=cookie(login("account-target",204)), second=cookie(login("account-target",204));
        String other=cookie(login("account-control",204));
        var lease=root.resolve(exporter.accountLeaseSelector(target.getId()));
        long now=Instant.now().getEpochSecond();
        String rid="0123456789abcdef0123456789abcdef";
        Files.createFile(lease,java.nio.file.attribute.PosixFilePermissions.asFileAttribute(java.nio.file.attribute.PosixFilePermissions.fromString("rw-------")));
        Files.writeString(lease,rid+" "+now+" "+(now+60));
        for(String session : new String[]{first,second})
            assertEquals(403,send(request("me").header("Cookie",session)).statusCode());
        login("account-target",403);
        assertEquals(200,send(request("me").header("Cookie",other)).statusCode());
        Files.writeString(lease,rid+" "+(now-20)+" "+(now-1));
        assertEquals(200,send(request("me").header("Cookie",first)).statusCode());
        Files.delete(lease);
        login("account-target",204);
    }
    User fixture(String name) {
        var u=new User(); u.setUsername(name); u.setRole(UserRole.STAFF);u.setPasswordSetupRequired(false);
        u.setPasswordHash(encoder.encode("FixturePassword1234"));return users.saveAndFlush(u);
    }

    @Test void revokeOnlyTheBoundSessionOverRealHttp() throws Exception {
        var u=new User(); u.setUsername("dev-lease");u.setRole(UserRole.STAFF);u.setPasswordSetupRequired(false);
        u.setPasswordHash(encoder.encode("FixturePassword1234")); users.saveAndFlush(u);
        String first=login(),second=login();
        var lease=root.resolve(exporter.sessionLeaseSelector(u.getId(),first.substring("JSESSIONID=".length())));
        long now=Instant.now().getEpochSecond();
        String id="0123456789abcdef0123456789abcdef";
        Files.createFile(lease,java.nio.file.attribute.PosixFilePermissions.asFileAttribute(java.nio.file.attribute.PosixFilePermissions.fromString("rw-------")));
        Files.writeString(lease,id+" "+(now-20)+" "+(now-1));
        assertEquals(200,send(request("me").header("Cookie",first)).statusCode());
        Files.writeString(lease,id+" "+now+" "+(now+60));
        assertEquals(401,send(request("me").header("Cookie",first)).statusCode());
        assertEquals(200,send(request("me").header("Cookie",second)).statusCode());
        Files.delete(lease);
        assertEquals(401,send(request("me").header("Cookie",first)).statusCode());
        assertEquals(200,send(request("me").header("Cookie",login())).statusCode());
    }
}
