package com.pbl4.studentweb.common.exception;

public class ResourceNotFoundException extends IllegalArgumentException {
    public ResourceNotFoundException(String resource) { super(resource + " not found"); }
}
