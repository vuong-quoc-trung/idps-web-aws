import test from "node:test";
import assert from "node:assert/strict";
import { lookupHybrid } from "../src/hybridLookup.ts";

const id = "f10d3db37e267d1b15f72fb8caf184df";
const row = {
  request_id: id,
  policy_action: "LOG_ONLY",
  automatic_block: false,
  final_risk: 45,
  rule_sources: ["NGINX", "SURICATA"],
  correlation_confidence: "REQUEST_TRANSACTION_MATCHED",
  evidence_ids: ["alert:17", "alert:18", "alert:17", "ai:18"],
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
    "Mô hình": "r37-hgb-uri100-v1",
    "Trạng thái": "SCORED",
    "Điểm bất thường": "0.125357",
    Ngưỡng: String(row.https_research.threshold),
    "Quyết định Hybrid": "LOG_ONLY",
    "Điểm rủi ro": "45",
    "Nguồn cảnh báo": "NGINX, SURICATA",
    "Tương quan": "REQUEST_TRANSACTION_MATCHED",
    "Chặn tự động": "Không",
  });
  assert.deepEqual(result.alertIds, [17, 18]);
});
test("missing incident, missing evidence and conflicting ID stay distinct", async () => {
  assert.match((await query([])).message, /Chưa có quyết định/);
  const fields = Object.fromEntries(
    (await query([{ ...row, https_research: null }])).fields,
  );
  assert.match(fields["Trạng thái"], /Chưa có kết quả AI/);
  assert.equal(fields["Điểm bất thường"], "—");
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
