import type { ReactNode } from "react";

type EmptyStateTone = "default" | "info" | "warning" | "danger" | "success";

interface EmptyStateProps {
  icon?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  tone?: EmptyStateTone;
  spacious?: boolean;
  className?: string;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  tone = "default",
  spacious = false,
  className = "",
}: EmptyStateProps) {
  const cls = ["empty-state", `empty-state--${tone}`, spacious ? "empty-state--spacious" : "", className]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={cls}>
      {icon && <span className="empty-state__icon">{icon}</span>}
      <p className="empty-state__title">{title}</p>
      {description && <p className="empty-state__description">{description}</p>}
      {action && <div className="empty-state__action">{action}</div>}
    </div>
  );
}
