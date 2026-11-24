package com.pbl4.studentweb;

import java.nio.file.Files;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import static org.junit.jupiter.api.Assertions.assertEquals;

@ActiveProfiles(value="native-lease-test", inheritProfiles=false)
class NativeLeaseHttpTests extends DevSessionLeaseHttpTests {
    @DynamicPropertySource static void nativeSettings(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", () -> "jdbc:h2:mem:nativelease;MODE=PostgreSQL");
        registry.add("app.native.session-lease-dir", root::toString);
        registry.add("app.native.lab-user-ids", () -> "1,2,3,4");
    }

    @Override @Test void revokeOnlyTheBoundSessionOverRealHttp() throws Exception {
        var actor = fixture("dev-lease");
        var first = login();
        var other = login();
        var target = root.resolve(exporter.sessionLeaseSelector(actor.getId(), first.substring("JSESSIONID=".length())));
        var now = Instant.now().getEpochSecond();
        Files.createFile(target, java.nio.file.attribute.PosixFilePermissions.asFileAttribute(
                java.nio.file.attribute.PosixFilePermissions.fromString("rw-------")));
        Files.writeString(target, "0123456789abcdef0123456789abcdef " + now + " " + (now+30));
        assertEquals(403,send(request("me").header("Cookie",first)).statusCode());
        assertEquals(200,send(request("me").header("Cookie",other)).statusCode());
        Files.delete(target);
        assertEquals(200,send(request("me").header("Cookie",first)).statusCode());
    }
}
