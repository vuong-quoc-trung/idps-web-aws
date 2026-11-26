import assert from "node:assert/strict";
import test from "node:test";
import {createElement} from "react";
import {renderToStaticMarkup} from "react-dom/server";
import {FirewallSync} from "../src/FirewallSync.ts";

for (const compact of [true,false]) {
  test(compact ? "overview and status badge" : "firewall banner", () => {
    const render = (report) => renderToStaticMarkup(createElement(FirewallSync,{report,compact}));
    for (const report of [undefined, {in_sync:false}, {status:"UNVERIFIED", reason:"JOURNAL_UNAVAILABLE"}]) {
      const html = render(report);
      assert.match(html,/Chưa xác minh/);
      assert.doesNotMatch(html,/class="error"|Chưa đồng bộ/);
    }
    assert.match(render({status:"SYNCED",differences:[]}),/Đã xác minh và đồng bộ/);
    assert.match(render({status:"OUT_OF_SYNC",differences:[]}),/Chưa đồng bộ/);
    const html = render({status:"OUT_OF_SYNC",differences:["192.168.1.19 · thiếu trong kernel"]});
    assert.match(html,/Chưa đồng bộ/);
    assert.match(html,/192.168.1.19/);
  });
}
