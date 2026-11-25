import assert from "node:assert/strict";
import test from "node:test";
import { followAlerts } from "../src/alertStream.ts";

test("split frames, heartbeat, reconnect snapshot and revoked session", async () => {
  const original = globalThis.fetch;
  let requests = 0,
    changes = 0,
    expired = 0;
  const states = [],
    events = [];
  globalThis.fetch = async (url, options) => {
    assert.equal(url, "/api/events");
    assert.equal(options.headers.Authorization, "Bearer test");
    if (++requests === 3) return new Response(null, { status: 401 });
    const chunks =
      requests === 1
        ? [
            ": heartbeat\n\nevent: res",
            "ync\ndata: {}\n\nevent: alert.created\ndata: 1\n\n",
          ]
        : ["event: resync\ndata: {}\n\n"];
    return new Response(
      new ReadableStream({
        start(ctrl) {
          for (const chunk of chunks)
            ctrl.enqueue(new TextEncoder().encode(chunk));
          ctrl.close();
        },
      }),
      { headers: { "Content-Type": "text/event-stream" } },
    );
  };
  try {
    await followAlerts(
      "test",
      new AbortController().signal,
      (id) => {
        changes++;
        events.push(id);
      },
      () => expired++,
      (value) => states.push(value),
    );
    assert.deepEqual(events, [null, 1, null]);
    assert.deepEqual(states, [
      "connecting",
      "connected",
      "disconnected",
      "reconnecting",
      "connected",
      "disconnected",
      "reconnecting",
      "disconnected",
    ]);
    assert.deepEqual([requests, changes, expired], [3, 3, 1]);
  } finally {
    globalThis.fetch = original;
  }
});
