import { useEffect, useState } from "react";

const options = { timeZone: "Asia/Ho_Chi_Minh" };
const time = new Intl.DateTimeFormat("en-GB", {
  ...options,
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});
const date = new Intl.DateTimeFormat("en-GB", {
  ...options,
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

export function RealtimeClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return (
    <time dateTime={now.toISOString()} title="Giờ Việt Nam (UTC+7)">
      <strong>{time.format(now)}</strong> {date.format(now)}
    </time>
  );
}
