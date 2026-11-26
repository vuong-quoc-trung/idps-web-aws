import test from "node:test";
import assert from "node:assert/strict";
import { lookupHybrid } from "../src/hybridLookup.ts";

const id = "f10d3db37e267d1b15f72fb8caf184df";
const row = {
  request_id: id,
  status: "SCORED",
  score: 0.125357,
  hybrid: "LOG_ONLY",
};
function query(result) {
  const signal = new AbortController().signal;
  return lookupHybrid(
    async (path, options) => {
      assert.equal(path, "/api/ai?request_id=" + id);
      assert.equal(options.signal, signal);
      return { result };
    },
    id,
    signal,
  );
}
test("lookup returns the bound AI result and Hybrid decision", async () => {
  assert.deepEqual(await query(row), row);
  assert.equal(await query(null), null);
});
test("lookup refuses an inconsistent request ID", async () => {
  await assert.rejects(query({ ...row, request_id: "other" }), /không khớp/);
});
