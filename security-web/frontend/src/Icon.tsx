/** Small, consistent outline icons. Labels remain on their parent controls. */
const paths: Record<string, string> = {
  overview: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  alerts: "M12 3 2.5 20h19L12 3Z M12 9v5 M12 17v.1",
  blocked: "M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6l-8-3Z M9 12l2 2 4-4",
  audit: "M8 3h8l4 4v14H4V3h4 M14 3v5h6 M8 12h8 M8 16h5",
  rules: "M4 6h16 M4 12h16 M4 18h16 M8 3v6 M16 9v6 M10 15v6",
  status: "M2 12h4l3-8 6 16 3-8h4",
  refresh:
    "M20 7a8 8 0 0 0-14-1L3 9 M3 3v6h6 M4 17a8 8 0 0 0 14 1l3-3 M21 21v-6h-6",
  logout: "M9 4H4v16h5 M9 12h12 M17 8l4 4-4 4",
  arrow: "M5 12h14 M14 7l5 5-5 5",
  network: "M9 3h6v6H9z M3 16h6v5H3z M15 16h6v5h-6z M12 9v4 M6 16v-3h12v3",
  clock: "M12 8v5l3 2 M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z",
};
export function Icon({
  name,
  className = "",
}: {
  name: string;
  className?: string;
}) {
  return (
    <svg
      className={`icon ${className}`}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={paths[name] ?? paths.blocked} />
    </svg>
  );
}
