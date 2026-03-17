import { useState, useEffect } from "react";

interface NotificationItem {
  id: string;
  text: string;
}

export function NotificationMarquee() {
  const [items, setItems] = useState<NotificationItem[]>([]);

  // Placeholder: in a real app, fetch notifications from API or WebSocket
  useEffect(() => {
    setItems([
      { id: "1", text: "系统已就绪，欢迎使用 Tender AI 智能投标平台" },
      { id: "2", text: "提示：上传招标文件后，AI 将自动解析关键条款" },
    ]);
  }, []);

  if (items.length === 0) return null;

  // Duplicate items for seamless loop
  const doubled = [...items, ...items];

  return (
    <div className="marquee-bar">
      <div className="marquee-track">
        {doubled.map((item, i) => (
          <span key={`${item.id}-${i}`} className="marquee-item">
            <span className="marquee-dot" />
            {item.text}
          </span>
        ))}
      </div>
    </div>
  );
}
