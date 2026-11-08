package com.pbl4.studentweb.common.web;

import com.pbl4.studentweb.common.exception.ResourceNotFoundException;
import jakarta.validation.ConstraintViolationException;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.HttpMediaTypeNotSupportedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice
public class ApiExceptionHandler {
    public record ApiError(int status, String message) {}

    @ExceptionHandler(ResourceNotFoundException.class)
    ResponseEntity<ApiError> notFound(ResourceNotFoundException e) { return error(404, e.getMessage()); }

    @ExceptionHandler({MethodArgumentNotValidException.class, ConstraintViolationException.class,
            HttpMessageNotReadableException.class, MethodArgumentTypeMismatchException.class})
    ResponseEntity<ApiError> invalidRequest(Exception e) { return error(400, "Invalid request data"); }

    // Complete this API error in the original dispatch. sendError would redispatch
    // to protected /error after the audit filter recorded 415, masking it as 401.
    @ExceptionHandler(HttpMediaTypeNotSupportedException.class)
    ResponseEntity<ApiError> unsupportedMedia(HttpMediaTypeNotSupportedException e) {
        return ResponseEntity.status(415).headers(e.getHeaders())
                .body(new ApiError(415, "Unsupported media type"));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    ResponseEntity<ApiError> invalid(IllegalArgumentException e) { return error(400, e.getMessage()); }

    @ExceptionHandler(IllegalStateException.class)
    ResponseEntity<ApiError> conflict(IllegalStateException e) { return error(409, e.getMessage()); }

    @ExceptionHandler(DataIntegrityViolationException.class)
    ResponseEntity<ApiError> integrity(DataIntegrityViolationException e) {
        return error(409, "Data is duplicated or still referenced by another record");
    }

    private ResponseEntity<ApiError> error(int status, String message) {
        return ResponseEntity.status(status).body(new ApiError(status, message));
    }
}
