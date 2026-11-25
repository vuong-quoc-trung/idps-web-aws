// Backend emits LF-delimited SSE. Decode incrementally across HTTP chunks.
export type StreamState =
  "connecting" | "connected" | "reconnecting" | "disconnected";

export async function followAlerts(
  token: string,
  signal: AbortSignal,
  changed: (id: number | null) => void,
  expired: () => void,
  state: (value: StreamState) => void,
) {
  let delay = 500;
  let first = true;
  while (!signal.aborted) {
    state(first ? "connecting" : "reconnecting");
    first = false;
    try {
      const response = await fetch("/api/events", {
        signal,
        headers: {
          Authorization: "Bearer " + token,
          Accept: "text/event-stream",
        },
      });
      if (signal.aborted) return;
      if ([401, 403].includes(response.status)) {
        state("disconnected");
        expired();
        return;
      }
      if (
        !response.ok ||
        !response.body ||
        !response.headers.get("content-type")?.startsWith("text/event-stream")
      )
        throw Error("Stream unavailable");
      const reader = response.body
        .pipeThrough(new TextDecoderStream())
        .getReader();
      state("connected");
      let buffer = "";
      try {
        while (!signal.aborted) {
          const { done, value } = await reader.read();
          if (done || signal.aborted) break;
          buffer += value;
          let end;
          while ((end = buffer.indexOf("\n\n")) >= 0) {
            const frame = buffer.slice(0, end);
            buffer = buffer.slice(end + 2);
            if (/^event: ?(resync|alert\.created)$/m.test(frame)) {
              delay = 500;
              const id = /^data: ?(\d+)$/m.exec(frame);
              changed(
                /^event: ?alert\.created$/m.test(frame) &&
                  id &&
                  Number.isSafeInteger(Number(id[1]))
                  ? Number(id[1])
                  : null,
              );
            }
          }
        }
      } finally {
        reader.releaseLock();
      }
    } catch {
      if (signal.aborted) return;
    }
    if (signal.aborted) return;
    state("disconnected");
    await new Promise((resolve) =>
      setTimeout(resolve, delay + Math.random() * 250),
    );
    delay = Math.min(delay * 2, 10000);
  }
}
