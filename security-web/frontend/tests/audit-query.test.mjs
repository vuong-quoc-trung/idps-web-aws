import assert from "node:assert/strict";
import test from "node:test";
import { auditQuery, defaultAuditFilters } from "../src/auditQuery.ts";

test("local time is sent as UTC and the default covers the previous 24 hours", () => {
  const previous = process.env.TZ;
  try {
    for (const zone of ["Asia/Ho_Chi_Minh", "UTC", "America/New_York"]) {
      process.env.TZ = zone;
      const now = Date.parse("2026-10-26T00:00:00Z");
      const filters = defaultAuditFilters(now);
      const query = new URLSearchParams(auditQuery(filters, 0));
      assert.equal(query.get("from"), "2026-10-25T00:00:00.000Z");
      assert.equal(filters.source, "STUDENT_AUDIT");
      assert.equal(query.has("to"), false);
    }
  } finally {
    if (previous == null) delete process.env.TZ;
    else process.env.TZ = previous;
  }
});

test("exact request IDs, IPv6 and endpoint punctuation survive URL encoding", () => {
  const filters = {
    ...defaultAuditFilters(),
    from: "",
    source: "",
    client_ip: " 2001:db8::1 ",
    uri_path: "/api/students/[id]%_&source=NGINX",
    status_code: "401",
    http_method: "POST",
    request_id: "request:one-two_3.4",
  };
  const query = new URLSearchParams(auditQuery(filters, 25));
  assert.equal(query.get("client_ip"), "2001:db8::1");
  assert.equal(query.get("uri_path"), filters.uri_path);
  assert.equal(query.has("source"), false);
  assert.equal(query.has("from"), false);
  assert.equal(query.get("request_id"), filters.request_id);
  assert.equal(query.get("status_code"), "401");
  assert.equal(query.get("http_method"), "POST");
  assert.equal(query.get("offset"), "25");
  assert.equal(query.get("limit"), "25");
});

test("invalid and reversed dates fail before a request is submitted", () => {
  const filters = defaultAuditFilters();
  assert.throws(() => auditQuery({ ...filters, from: "invalid-date" }, 0));
  assert.throws(() =>
    auditQuery(
      { ...filters, from: "2026-10-26T10:00", to: "2026-10-26T09:00" },
      0,
    ),
  );
  assert.throws(() =>
    auditQuery(
      { ...filters, from: "2026-10-26T10:00", to: "2026-10-26T10:00" },
      0,
    ),
  );
  const query = new URLSearchParams(
    auditQuery({ ...filters, from: "", to: "2026-10-26T10:00" }, 0),
  );
  assert.ok(query.get("to")?.endsWith("Z"));
  assert.equal(query.has("from"), false);
});
