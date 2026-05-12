import type { ReactNode } from "react";

interface ToolbarProps {
  children: ReactNode;
  align?: "start" | "between" | "end";
  className?: string;
}

export function Toolbar({ children, align = "between", className = "" }: ToolbarProps) {
  return <div className={`toolbar-row toolbar-row--${align} ${className}`.trim()}>{children}</div>;
}
