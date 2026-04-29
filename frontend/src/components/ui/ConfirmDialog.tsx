import { useEffect } from "react";

import { ClayButton } from "./ClayButton";

type ConfirmDialogProps = {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  confirmVariant?: "primary" | "danger";
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "确认",
  cancelLabel = "取消",
  confirmVariant = "danger",
  busy = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  useEffect(() => {
    if (!open) return undefined;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) {
        onCancel();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [busy, onCancel, open]);

  if (!open) return null;

  return (
    <div className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="confirm-dialog-title">
      <div className="confirm-dialog__backdrop" onClick={busy ? undefined : onCancel} />
      <div className="confirm-dialog__panel">
        <div className="confirm-dialog__content">
          <h2 id="confirm-dialog-title">{title}</h2>
          <p>{description}</p>
        </div>
        <div className="confirm-dialog__actions">
          <ClayButton type="button" variant="ghost" onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </ClayButton>
          <ClayButton type="button" variant={confirmVariant} onClick={onConfirm} disabled={busy}>
            {busy ? "处理中..." : confirmLabel}
          </ClayButton>
        </div>
      </div>
    </div>
  );
}
