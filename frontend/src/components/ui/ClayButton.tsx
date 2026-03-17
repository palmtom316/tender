import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "ghost" | "outline" | "danger";
type Size = "sm" | "md" | "lg";

interface ClayButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  children: ReactNode;
}

export function ClayButton({
  variant = "primary",
  size = "md",
  className = "",
  children,
  ...rest
}: ClayButtonProps) {
  const cls = [
    "clay-btn",
    `clay-btn--${variant}`,
    size !== "md" ? `clay-btn--${size}` : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button className={cls} {...rest}>
      {children}
    </button>
  );
}
