import test from "node:test";
import assert from "node:assert/strict";
import { sourceIpLabel } from "../src/sourceIp.ts";
test("post-proxy source never silently falls back to proxy", () => {
  const a = {
    source: "SURICATA",
    src_ip: "192.168.20.1",
    suricata_post_proxy: true,
  };
  assert.equal(sourceIpLabel(a), "Chưa xác minh");
  assert.equal(
    sourceIpLabel({
      ...a,
      client_ip: "192.168.10.10",
      client_ip_verified: true,
    }),
    "192.168.10.10 (Đã xác minh)",
  );
  assert.equal(
    sourceIpLabel({ ...a, network_src_ip: "127.77.0.1" }),
    "Chưa xác minh",
  );
  assert.equal(
    sourceIpLabel({ ...a, network_src_ip: "192.0.2.12" }),
    "192.0.2.12 (IP mạng)",
  );
  assert.equal(
    sourceIpLabel({
      ...a,
      client_ip: "192.168.10.10",
      client_ip_verified: false,
    }),
    "Chưa xác minh",
  );
});
test("legacy network identity and other sources remain distinct", () => {
  assert.equal(
    sourceIpLabel({ source: "SURICATA", src_ip: "192.168.10.10" }),
    "192.168.10.10 (IP mạng / lịch sử)",
  );
  assert.equal(
    sourceIpLabel({ source: "NGINX", src_ip: "192.168.10.10" }),
    "192.168.10.10",
  );
});
