package com.pbl4.studentweb;

import com.pbl4.studentweb.accesslog.service.SecurityAuditService;
import java.net.CookieManager;
import java.net.CookiePolicy;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.UUID;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import tools.jackson.databind.json.JsonMapper;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.timeout;
import static org.mockito.Mockito.verify;

/** Real embedded HTTP: MockMvc does not perform the container's ERROR redispatch. */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT, properties = {
    "spring.datasource.url=jdbc:h2:mem:wirestatus;MODE=PostgreSQL;DB_CLOSE_DELAY=-1",
    "spring.datasource.username=sa", "spring.datasource.password=",
    "spring.jpa.hibernate.ddl-auto=create-drop", "spring.jpa.properties.hibernate.default_schema=PUBLIC",
    "app.security.rate-limit-enabled=false", "app.bootstrap.enabled=false", "logging.level.root=WARN"
})
class HttpErrorStatusTests {
    @Autowired Environment environment;
    @Autowired JsonMapper json;
    @MockitoBean SecurityAuditService audit;
    @MockitoBean com.pbl4.studentweb.user.service.PasswordSetupService passwords;
    @org.springframework.test.context.bean.override.mockito.MockitoSpyBean
    org.springframework.security.crypto.password.PasswordEncoder encoder;

    URI uri(String path) {
        return URI.create("http://127.0.0.1:" + environment.getProperty("local.server.port") + path);
    }

    HttpClient client() {
        return HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1).connectTimeout(Duration.ofSeconds(5))
                .cookieHandler(new CookieManager(null, CookiePolicy.ACCEPT_ALL)).build();
    }

    HttpRequest.Builder request(String method, String path, String body, String media, String id) {
        var request = HttpRequest.newBuilder(uri(path)).timeout(Duration.ofSeconds(10)).header("X-Request-Id", id);
        if (media != null) request.header("Content-Type", media);
        return request.method(method, body == null ? HttpRequest.BodyPublishers.noBody() : HttpRequest.BodyPublishers.ofString(body));
    }

    tools.jackson.databind.JsonNode csrf(HttpClient client) throws Exception {
        var response = client.send(HttpRequest.newBuilder(uri("/api/auth/csrf")).timeout(Duration.ofSeconds(10)).GET().build(), HttpResponse.BodyHandlers.ofString());
        assertThat(response.statusCode()).isEqualTo(200);
        return json.readTree(response.body());
    }

    @Test void unsupportedMediaIs415OnTheWireAndInTheAudit() throws Exception {
        var client = client(); var csrf = csrf(client); var id = UUID.randomUUID().toString().replace("-", "");
        var response = client.send(request("POST", "/api/auth/activate", "harmless probe", "application/octet-stream", id)
                .header(csrf.get("headerName").asString(), csrf.get("token").asString()).build(), HttpResponse.BodyHandlers.ofInputStream());
        try (var body = response.body()) {
            assertThat(response.statusCode()).isEqualTo(415);
            assertThat(response.headers().firstValue("X-Request-Id")).contains(id);
            var text = new String(body.readAllBytes(), java.nio.charset.StandardCharsets.UTF_8);
            assertThat(json.readTree(text).get("message").asString()).isEqualTo("Unsupported media type");
            assertThat(text).doesNotContain("harmless probe");
        }
        verify(audit, timeout(2000)).record(argThat(e -> id.equals(e.requestId()) && e.statusCode() == 415), any());
    }

    @Test void malformedJsonStillReturns400WithMatchingAudit() throws Exception {
        var client = client(); var csrf = csrf(client); var id = UUID.randomUUID().toString().replace("-", "");
        var response = client.send(request("POST", "/api/auth/activate", "{\"token\":", "application/json", id)
                .header(csrf.get("headerName").asString(), csrf.get("token").asString()).build(), HttpResponse.BodyHandlers.ofString());
        assertThat(response.statusCode()).isEqualTo(400);
        assertThat(response.headers().firstValue("X-Request-Id")).contains(id);
        verify(audit, timeout(2000)).record(argThat(e -> id.equals(e.requestId()) && e.statusCode() == 400), any());
    }

    @Test void csrfAndProtectedRoutesAreNotRelaxed() throws Exception {
        var client = client(); csrf(client);
        var response = client.send(request("POST", "/api/auth/activate", "harmless probe", "application/octet-stream", "missing-csrf")
                .build(), HttpResponse.BodyHandlers.ofString());
        assertThat(response.statusCode()).isEqualTo(403);
        for (String path : new String[]{"/api/auth/me", "/error"}) {
            response = client.send(HttpRequest.newBuilder(uri(path)).timeout(Duration.ofSeconds(10)).GET().build(), HttpResponse.BodyHandlers.ofString());
            assertThat(response.statusCode()).isEqualTo(401);
        }
    }

    @Test void malformedFormsReturn400BeforePasswordAuthentication() throws Exception {
        var client = client(); var csrf = csrf(client);
        org.mockito.Mockito.clearInvocations(encoder);
        for (String input : new String[]{"message=%FF", "message=%ZZ"}) {
            var id = UUID.randomUUID().toString().replace("-", "");
            var response = client.send(request("POST", "/api/auth/login", input, "application/x-www-form-urlencoded", id)
                    .header(csrf.get("headerName").asString(), csrf.get("token").asString()).build(), HttpResponse.BodyHandlers.ofInputStream());
            try (var body = response.body()) {
                assertThat(response.statusCode()).isEqualTo(400);
                assertThat(new String(body.readAllBytes(), java.nio.charset.StandardCharsets.UTF_8)).contains("Invalid request data").doesNotContain(input);
                assertThat(response.headers().firstValue("X-Request-Id")).contains(id);
            }
            verify(audit, timeout(2000)).record(argThat(e -> id.equals(e.requestId()) && e.statusCode() == 400), any());
        }
        org.mockito.Mockito.verify(encoder, org.mockito.Mockito.never()).matches(any(), any());
    }

    @Test void genuineServerFailureRemains500WithoutSensitiveErrorDisclosure() throws Exception {
        org.mockito.Mockito.doThrow(new RuntimeException("private-fault-detail"))
                .when(passwords).setInitialPassword("fixture-token", "Valid-test-password-123");
        var client = client(); var csrf = csrf(client); var id = UUID.randomUUID().toString().replace("-", "");
        var response = client.send(request("POST", "/api/auth/activate", "{\"token\":\"fixture-token\",\"password\":\"Valid-test-password-123\"}", "application/json", id)
                .header(csrf.get("headerName").asString(), csrf.get("token").asString()).build(), HttpResponse.BodyHandlers.ofInputStream());
        try (var body = response.body()) {
            assertThat(response.statusCode()).isEqualTo(500);
            assertThat(new String(body.readAllBytes(), java.nio.charset.StandardCharsets.UTF_8)).contains("Internal server error")
                    .doesNotContain("private-fault-detail", "fixture-token", "Valid-test-password-123", "Exception", "stackTrace");
        }
        verify(audit, timeout(2000)).record(argThat(e -> id.equals(e.requestId()) && e.statusCode() == 500), any());
    }
}
