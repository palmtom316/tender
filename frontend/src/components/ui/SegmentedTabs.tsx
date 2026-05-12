import { Badge } from "./Badge";

export interface SegmentedTabItem<T extends string> {
  id: T;
  label: string;
  count?: number;
  disabled?: boolean;
}

interface SegmentedTabsProps<T extends string> {
  ariaLabel: string;
  items: SegmentedTabItem<T>[];
  value: T;
  onChange: (value: T) => void;
  compact?: boolean;
  className?: string;
}

export function SegmentedTabs<T extends string>({
  ariaLabel,
  items,
  value,
  onChange,
  compact = false,
  className = "",
}: SegmentedTabsProps<T>) {
  return (
    <div className={`segmented-tabs ${compact ? "segmented-tabs--compact" : ""} ${className}`.trim()} role="tablist" aria-label={ariaLabel}>
      {items.map((item) => {
        const active = item.id === value;
        const label = item.count == null ? item.label : `${item.label} ${item.count}`;
        return (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={active}
            aria-label={label}
            disabled={item.disabled}
            className={`segmented-tab ${active ? "is-active" : ""}`}
            onClick={() => onChange(item.id)}
          >
            <span>{item.label}</span>
            {item.count != null && <Badge size="sm" variant={active ? "primary" : "default"}>{item.count}</Badge>}
          </button>
        );
      })}
    </div>
  );
}
