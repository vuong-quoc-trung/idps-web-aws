export default function ContentSkeleton({ label }: { label: string }) {
  return <div className="content-skeleton" role="status" aria-live="polite">
    <p>{label}</p>
    <div className="skeleton-heading" aria-hidden="true" />
    <div className="skeleton-grid" aria-hidden="true">
      {[0, 1, 2, 3].map(item => <div className="skeleton-card" key={item}><span /><span /><span /></div>)}
    </div>
  </div>;
}
