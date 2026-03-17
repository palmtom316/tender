import type { ReactNode } from "react";

type BadgeVariant = "default" | "primary" | "success" | "warning" | "danger" | "info";

interface BadgeProps {
  variant?: BadgeVariant;
  children: ReactNode;
  style?: React.CSSProperties;
}

export function Badge({ variant = "default", children, style }: BadgeProps) {
  return (
    <span className={`clay-badge clay-badge--${variant}`} style={style}>
      {children}
    </span>
  );
}
