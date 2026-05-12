import type { CSSProperties, HTMLAttributes, ReactNode } from "react";

type BadgeVariant = "default" | "primary" | "success" | "warning" | "danger" | "info";
type BadgeSize = "sm" | "md";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
  tone?: BadgeVariant;
  size?: BadgeSize;
  children: ReactNode;
  style?: CSSProperties;
}

export function Badge({ variant = "default", tone, size = "md", children, style, className = "", ...rest }: BadgeProps) {
  const resolvedVariant = tone ?? variant;
  return (
    <span
      className={`clay-badge clay-badge--${resolvedVariant} clay-badge--${size} ${className}`.trim()}
      style={style}
      {...rest}
    >
      {children}
    </span>
  );
}
