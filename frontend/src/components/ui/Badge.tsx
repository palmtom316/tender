import type { CSSProperties, HTMLAttributes, ReactNode } from "react";

type BadgeVariant = "default" | "primary" | "success" | "warning" | "danger" | "info";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
  children: ReactNode;
  style?: CSSProperties;
}

export function Badge({ variant = "default", children, style, className = "", ...rest }: BadgeProps) {
  return (
    <span
      className={`clay-badge clay-badge--${variant} ${className}`.trim()}
      style={style}
      {...rest}
    >
      {children}
    </span>
  );
}
