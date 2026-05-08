import { Badge } from "../../../../components/ui/Badge";

function diffDays(value: string): number {
  const now = new Date();
  const target = new Date(value);
  const ms = target.getTime() - now.getTime();
  return Math.ceil(ms / (1000 * 60 * 60 * 24));
}

export function ExpiryBadge({ value }: { value: string | null }) {
  if (!value) {
    return <Badge>无有效期</Badge>;
  }

  const days = diffDays(value);
  if (Number.isNaN(days)) {
    return <Badge>日期异常</Badge>;
  }
  if (days < 0) {
    return <Badge variant="danger">已过期 {Math.abs(days)} 天</Badge>;
  }
  if (days <= 30) {
    return <Badge variant="warning">{days} 天内到期</Badge>;
  }
  if (days <= 90) {
    return <Badge>{days} 天</Badge>;
  }
  return <Badge variant="success">{days} 天</Badge>;
}
