import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "ghost" | "outline" | "danger" | "secondary";
type Size = "sm" | "md" | "lg";

interface ClayButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  children: ReactNode;
}

export function ClayButton({
  variant = "primary",
  size = "md",
  loading = false,
  disabled,
  className = "",
  children,
  ...rest
}: ClayButtonProps) {
  const normalizedVariant = variant === "secondary" ? "outline" : variant;
  const cls = [
    "clay-btn",
    `clay-btn--${normalizedVariant}`,
    size !== "md" ? `clay-btn--${size}` : "",
    loading ? "is-loading" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button className={cls} disabled={disabled || loading} aria-busy={loading || undefined} {...rest}>
      {loading && <span className="clay-btn__spinner" aria-hidden="true" />}
      <span className="clay-btn__label">{loading ? "保存中" : children}</span>
    </button>
  );
}
