import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "ghost" | "outline" | "danger" | "secondary";
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
  const normalizedVariant = variant === "secondary" ? "outline" : variant;
  const cls = [
    "clay-btn",
    `clay-btn--${normalizedVariant}`,
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
