import { Icon } from "./Icon";

/** Presentational only: request lifecycle and empty-state conditions stay with callers. */
export function EmptyState({
  title,
  description,
}: {
  title: string;
  description?: string;
}) {
  return (
    <div className="empty-state">
      <Icon name="audit" />
      <div>
        <strong>{title}</strong>
        {description && <p>{description}</p>}
      </div>
    </div>
  );
}
