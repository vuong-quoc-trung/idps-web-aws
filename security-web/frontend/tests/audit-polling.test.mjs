import test from "node:test";
import assert from "node:assert/strict";
import { startAuditPolling } from "../src/auditPolling.ts";
const tick = () => new Promise((resolve) => setImmediate(resolve));
test("polling waits for completion, coalesces manual refresh and stops when hidden/unmounted", async () => {
  let visible = true,
    listener,
    scheduled,
    resolve,
    signal,
    calls = 0,
    unsubscribed = false;
  const poller = startAuditPolling({
    visible: () => visible,
    subscribe: (fn) => {
      listener = fn;
      return () => {
        unsubscribed = true;
      };
    },
    schedule: (fn) => {
      scheduled = fn;
      return 1;
    },
    cancel: () => {
      scheduled = undefined;
    },
    load: (s) => {
      calls++;
      signal = s;
      return new Promise((r) => {
        resolve = r;
      });
    },
  });
  assert.equal(calls, 1);
  assert.equal(scheduled, undefined);
  poller.refresh();
  poller.refresh();
  assert.equal(calls, 1);
  resolve();
  await tick();
  assert.equal(calls, 2);
  resolve();
  await tick();
  assert.equal(typeof scheduled, "function");
  scheduled();
  assert.equal(calls, 3);
  visible = false;
  listener();
  assert.equal(signal.aborted, true);
  resolve();
  await tick();
  assert.equal(scheduled, undefined);
  visible = true;
  listener();
  assert.equal(calls, 4);
  poller.stop();
  assert.equal(signal.aborted, true);
  assert.equal(unsubscribed, true);
  resolve();
  await tick();
  assert.equal(scheduled, undefined);
  poller.refresh();
  assert.equal(calls, 4);
});
test("hidden mount waits until visible; remount loads again", async () => {
  let visible = false,
    listener,
    calls = 0;
  const options = {
    visible: () => visible,
    subscribe: (fn) => {
      listener = fn;
      return () => {};
    },
    load: async () => {
      calls++;
    },
    schedule: () => 1,
    cancel: () => {},
  };
  const first = startAuditPolling(options);
  assert.equal(calls, 0);
  visible = true;
  listener();
  await tick();
  assert.equal(calls, 1);
  first.stop();
  const second = startAuditPolling(options);
  await tick();
  assert.equal(calls, 2);
  second.stop();
});
