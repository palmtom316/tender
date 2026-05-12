interface LoadingStateProps {
  label: string;
  rows?: number;
  compact?: boolean;
}

export function LoadingState({ label, rows = 2, compact = false }: LoadingStateProps) {
  return (
    <div className={`skeleton-stack ${compact ? "skeleton-stack--compact" : ""}`} aria-label={label}>
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className={index === 0 ? "skeleton-card" : "skeleton-line"} />
      ))}
    </div>
  );
}
