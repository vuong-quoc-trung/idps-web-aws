import test from "node:test";
import assert from "node:assert/strict";
import { freshness, ruleDeployment, triageLabels } from "../src/operations.ts";
test("freshness distinguishes silence, missing timestamps and future clocks", () => {
  const now = "2026-11-07T00:10:00Z";
  assert.match(freshness(null, now), /Chưa ghi nhận/);
  assert.match(freshness("2026-11-07T00:09:30Z", now), /phút gần đây/);
  assert.match(freshness("2026-11-07T00:00:00Z", now), /10 phút/);
  assert.match(freshness("2026-11-07T00:11:00Z", now), /đồng hồ/);
  assert.match(freshness("invalid", now), /Chưa xác định/);
});
test("matching deployed file never claims the sensor has loaded it", () => {
  assert.match(
    ruleDeployment({
      deployment: "UNVERIFIED",
      deployed_file_matches_build: true,
    }),
    /chưa xác minh đã nạp/,
  );
  assert.match(
    ruleDeployment({
      deployment: "UNVERIFIED",
      deployed_file_matches_build: false,
    }),
    /khác bản build/,
  );
  assert.match(ruleDeployment({ deployment: "BUILT_IN" }), /backend đang chạy/);
  assert.equal(Object.keys(triageLabels).length, 4);
});
