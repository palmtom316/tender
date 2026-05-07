import type { CSSProperties } from "react";

export type ProgressTone = "default" | "active" | "success" | "danger";

export type ProgressMeta = {
  percent: number;
  label: string;
  hint: string;
  tone: ProgressTone;
};

type ProgressFillStyle = CSSProperties & {
  "--standard-progress-percent": string;
};

type ProgressBarProps = {
  meta: ProgressMeta;
  role?: string;
  ariaLive?: "polite" | "assertive";
};

export function ProgressBar({ meta, role, ariaLive }: ProgressBarProps) {
  return (
    <div
      className={`standard-progress standard-progress--${meta.tone}`}
      role={role}
      aria-live={ariaLive}
    >
      <div className="standard-progress__top">
        <span className="standard-progress__label">{meta.label}</span>
        <span className="standard-progress__percent">{meta.percent}%</span>
      </div>
      <div className="standard-progress__track">
        <div
          className="standard-progress__fill"
          style={{ "--standard-progress-percent": `${meta.percent}%` } as ProgressFillStyle}
        />
      </div>
      <div className="standard-progress__hint">{meta.hint}</div>
    </div>
  );
}
