import { useState, useEffect } from "react";

interface NotificationItem {
  id: string;
  text: string;
}

export function NotificationMarquee() {
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [paused, setPaused] = useState(false);

  // Placeholder: in a real app, fetch notifications from API or WebSocket
  useEffect(() => {
    setItems([
      { id: "1", text: "系统已就绪，欢迎使用 Tender AI 智能投标平台" },
      { id: "2", text: "提示：上传 ZIP 文件包或 PDF 后，系统会先解析文档结构；AI 抽取需手动启动" },
    ]);
  }, []);

  if (items.length === 0) return null;

  // Duplicate items for seamless loop
  const doubled = [...items, ...items];

  return (
    <div className="marquee-bar">
      <button
        type="button"
        className="marquee-pause"
        onClick={() => setPaused((value) => !value)}
        aria-pressed={paused}
      >
        {paused ? "继续通知" : "暂停通知"}
      </button>
      <div className={`marquee-track ${paused ? "is-paused" : ""}`} aria-live="polite">
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
