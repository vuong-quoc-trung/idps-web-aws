/** One request at a time; the delay starts after completion, never at dispatch. */
export function startAuditPolling({
  load,
  visible,
  subscribe,
  schedule = (callback: () => void) => setTimeout(callback, 5000),
  cancel = (timer: ReturnType<typeof setTimeout>) => clearTimeout(timer),
}: {
  load: (signal: AbortSignal) => Promise<void>;
  visible: () => boolean;
  subscribe: (callback: () => void) => () => void;
  schedule?: (callback: () => void) => ReturnType<typeof setTimeout>;
  cancel?: (timer: ReturnType<typeof setTimeout>) => void;
}) {
  let stopped = false;
  let active: AbortController | null = null;
  let pending = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  function clear() {
    if (timer !== undefined) cancel(timer);
    timer = undefined;
  }
  async function run() {
    clear();
    if (stopped || !visible()) return;
    if (active) {
      pending = true;
      return;
    }
    const controller = new AbortController();
    active = controller;
    try {
      await load(controller.signal);
    } finally {
      active = null;
      if (!stopped && visible()) {
        if (pending) {
          pending = false;
          void run();
        } else timer = schedule(() => void run());
      }
    }
  }
  const unsubscribe = subscribe(() => {
    clear();
    if (visible()) void run();
    else {
      pending = false;
      active?.abort();
    }
  });
  void run();
  return {
    refresh: () => void run(),
    stop() {
      stopped = true;
      clear();
      active?.abort();
      unsubscribe();
    },
  };
}
