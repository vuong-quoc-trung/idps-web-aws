package com.pbl4.studentweb.configuration;

import com.pbl4.studentweb.accesslog.service.SecuritySignals;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.lang.reflect.Type;
import java.util.Set;
import org.springframework.core.MethodParameter;
import org.springframework.http.HttpInputMessage;
import org.springframework.http.HttpHeaders;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;
import org.springframework.web.servlet.mvc.method.annotation.RequestBodyAdviceAdapter;
import tools.jackson.databind.json.JsonMapper;

/** Reject forbidden top-level authority/ownership fields before DTO binding; never log body values. */
@ControllerAdvice
public class ProtectedFieldAdvice extends RequestBodyAdviceAdapter {
    private static final int MAX_BYTES = 1024 * 1024;
    private static final Set<String> PROTECTED = Set.of("role", "isAdmin", "ownerId", "userId", "studentId", "authorities", "permissions");
    private final JsonMapper mapper;
    public ProtectedFieldAdvice(JsonMapper mapper) { this.mapper = mapper; }
    @Override public boolean supports(MethodParameter parameter, Type targetType, Class<? extends HttpMessageConverter<?>> converter) {
        return parameter.getContainingClass().getPackageName().startsWith("com.pbl4.studentweb.")
                && targetType instanceof Class<?> dto && dto.isRecord();
    }
    @Override public HttpInputMessage beforeBodyRead(HttpInputMessage input, MethodParameter parameter, Type targetType,
            Class<? extends HttpMessageConverter<?>> converter) throws IOException {
        if (input.getHeaders().getContentType() == null || !input.getHeaders().getContentType().isCompatibleWith(org.springframework.http.MediaType.APPLICATION_JSON)) return input;
        byte[] bytes = input.getBody().readNBytes(MAX_BYTES + 1);
        if (bytes.length > MAX_BYTES) throw new HttpMessageNotReadableException("Request data too large", input);
        tools.jackson.databind.JsonNode tree = null;
        try { tree = mapper.readTree(bytes); } catch (RuntimeException malformed) { /* Normal DTO parsing reports malformed JSON. */ }
        boolean forbidden = false;
        if (tree != null && tree.isObject() && RequestContextHolder.getRequestAttributes() instanceof ServletRequestAttributes attrs) {
            for (String field : PROTECTED) {
                // Role is intentionally writable only in the admin-only CreateUserRequest DTO.
                boolean allowed = field.equals("role") && targetType == com.pbl4.studentweb.user.dto.CreateUserRequest.class;
                if (!allowed && tree.has(field)) {
                    SecuritySignals.get(attrs.getRequest()).forbiddenField(field);
                    forbidden = true;
                }
            }
        }
        if (forbidden) throw new HttpMessageNotReadableException("Forbidden request field", input);
        return new HttpInputMessage() {
            public HttpHeaders getHeaders() { return input.getHeaders(); }
            public java.io.InputStream getBody() { return new ByteArrayInputStream(bytes); }
        };
    }
}
