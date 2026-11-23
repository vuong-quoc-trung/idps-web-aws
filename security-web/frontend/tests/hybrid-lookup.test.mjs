import test from "node:test";
import assert from "node:assert/strict";
import { lookupHybrid } from "../src/hybridLookup.ts";

const id = "f10d3db37e267d1b15f72fb8caf184df";
const row = {
  request_id: id,
  policy_action: "LOG_ONLY",
  automatic_block: false,
  https_research: {
    request_id: id,
    model_id: "r37-hgb-uri100-v1",
    status: "SCORED",
    score: 0.1253570318222046,
    threshold: 0.7664756774902344,
  },
};
function query(incidents) {
  const signal = new AbortController().signal;
  return lookupHybrid(
    async (path, options) => {
      assert.equal(path, "/api/hybrid-incidents?request_id=" + id);
      assert.equal(options.signal, signal);
      return { incidents };
    },
    id,
    signal,
  );
}
test("R37 lookup shows the exact incident and its Hybrid policy", async () => {
  const result = await query([{ ...row, request_id: "other" }, row]);
  assert.deepEqual(Object.fromEntries(result.fields), {
    "Request ID": id,
    Model: "r37-hgb-uri100-v1",
    "Trạng thái": "SCORED",
    "AI Score": "0.125357",
    Threshold: String(row.https_research.threshold),
    "Hybrid Policy": "LOG_ONLY",
    automatic_block: "false",
  });
});
test("missing incident, missing evidence and conflicting ID stay distinct", async () => {
  assert.match((await query([])).message, /Chưa có quyết định/);
  const fields = Object.fromEntries(
    (await query([{ ...row, https_research: null }])).fields,
  );
  assert.match(fields["Trạng thái"], /Chưa có bằng chứng/);
  assert.equal(fields["AI Score"], "—");
  assert.match(
    (
      await query([
        {
          ...row,
          https_research: { ...row.https_research, request_id: "other" },
        },
      ])
    ).message,
    /không khớp/,
  );
});
