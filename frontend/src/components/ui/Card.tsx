import type { ReactNode, HTMLAttributes } from "react";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  clickable?: boolean;
  flat?: boolean;
  children: ReactNode;
}

export function Card({
  clickable,
  flat,
  className = "",
  children,
  ...rest
}: CardProps) {
  const cls = [
    "clay-card",
    clickable ? "clay-card--clickable" : "",
    flat ? "clay-card--flat" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={cls} {...rest}>
      {children}
    </div>
  );
}
