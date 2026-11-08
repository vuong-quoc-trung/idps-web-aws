export type AlertUpdates = {
  watermark: number;
  count: number;
  severity: number | null;
  items: { id: number; severity: number }[];
};
/** Session-memory cursor; first successful snapshot is a silent baseline. */
export function createAlertTracker() {
  let cursor: number | null = null;
  return {
    cursor: () => cursor,
    accept(update: AlertUpdates | undefined) {
      if (
        !update ||
        !Number.isSafeInteger(update.watermark) ||
        update.watermark < 0
      )
        return null;
      const previous = cursor;
      cursor = Math.max(cursor ?? 0, update.watermark);
      if (previous === null || update.watermark <= previous || !update.count)
        return null;
      return update;
    },
    reset() {
      cursor = null;
    },
  };
}
