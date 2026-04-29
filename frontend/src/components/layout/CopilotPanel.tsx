import { useState, useEffect, useCallback, useRef } from "react";
import { Icon } from "../ui/Icon";

interface Message {
  role: "user" | "assistant";
  content: string;
}

export function CopilotPanel() {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Message[]>([
    { role: "assistant", content: "你好！我是 Tender AI 助手，有什么可以帮你的吗？" },
  ]);
  const responseTimeoutRef = useRef<ReturnType<typeof setTimeout>>();

  // Keyboard shortcut: Ctrl+/
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.key === "/") {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  // Cleanup pending response timeout on unmount
  useEffect(() => {
    return () => clearTimeout(responseTimeoutRef.current);
  }, []);

  const handleSend = useCallback(() => {
    const text = input.trim();
    if (!text) return;

    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");

    // Placeholder response
    responseTimeoutRef.current = setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "收到您的问题，AI 功能即将上线，敬请期待。" },
      ]);
    }, 500);
  }, [input]);

  return (
    <>
      {!open && (
        <button
          className="copilot-trigger"
          onClick={() => setOpen(true)}
          title="打开 AI 助手 (Ctrl+/)"
          aria-label="打开 AI 助手"
        >
          AI
        </button>
      )}

      {open && (
        <div className="copilot-backdrop visible" onClick={() => setOpen(false)} aria-hidden="true" />
      )}

      <div className={`copilot-panel ${open ? "open" : ""}`} role="complementary" aria-label="AI 助手" hidden={!open}>
        <div className="copilot-header">
          <h3>AI 助手</h3>
          <button className="copilot-close" onClick={() => setOpen(false)} aria-label="关闭 AI 助手">
            <Icon name="x" size={16} />
          </button>
        </div>

        <div className="copilot-messages" role="log" aria-live="polite" aria-relevant="additions text">
          {messages.map((msg, i) => (
            <div key={i} className={`copilot-bubble ${msg.role}`}>
              {msg.content}
            </div>
          ))}
        </div>

        <div className="copilot-input-area">
          <input
            className="copilot-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder="输入问题..."
            aria-label="输入问题"
          />
          <button className="copilot-send" onClick={handleSend} aria-label="发送问题">
            <Icon name="send" size={14} />
          </button>
        </div>
      </div>
    </>
  );
}
