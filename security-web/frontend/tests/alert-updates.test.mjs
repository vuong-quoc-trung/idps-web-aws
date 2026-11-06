import test from "node:test";
import assert from "node:assert/strict";
import { createAlertTracker } from "../src/alertUpdates.ts";
const report = (watermark, count = 1) => ({
  watermark,
  count,
  severity: 1,
  items: [{ id: watermark, severity: 1 }],
});
test("silent baseline, exactly once, out-of-order responses and missing/error reports", () => {
  const t = createAlertTracker();
  assert.equal(t.accept(report(12)), null);
  assert.equal(t.accept(report(12)), null);
  assert.equal(t.accept(undefined), null);
  assert.equal(t.accept(report(15)).watermark, 15);
  assert.equal(t.accept(report(14)), null);
  assert.equal(t.accept(report(15)), null);
  assert.equal(t.cursor(), 15);
});
test("cursor survives filter/navigation changes; reset makes next login silent", () => {
  const t = createAlertTracker();
  t.accept(report(100));
  assert.equal(t.accept(report(100)), null);
  assert.equal(t.accept(report(130, 30)).count, 30);
  t.reset();
  assert.equal(t.cursor(), null);
  assert.equal(t.accept(report(150)), null);
});
