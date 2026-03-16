import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

interface TableOverrideEditorProps {
  tableId: string;
  originalJson: unknown;
  currentOverride: unknown;
}

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
const TOKEN = localStorage.getItem("tender_token") ?? "dev-token";

async function submitOverride(tableId: string, overrideJson: object): Promise<unknown> {
  const res = await fetch(`${BASE_URL}/api/tables/${tableId}/override`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ override_json: overrideJson }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export function TableOverrideEditor({ tableId, originalJson, currentOverride }: TableOverrideEditorProps) {
  const effectiveJson = currentOverride ?? originalJson;
  const [text, setText] = useState(JSON.stringify(effectiveJson, null, 2));
  const [parseError, setParseError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: (json: object) => submitOverride(tableId, json),
  });

  const handleSave = () => {
    try {
      const parsed = JSON.parse(text);
      setParseError(null);
      mutation.mutate(parsed);
    } catch {
      setParseError("JSON 格式错误");
    }
  };

  return (
    <div className="card" style={{ padding: 16 }}>
      <div className="editor-toolbar">
        <h3 style={{ margin: 0 }}>表格纠错</h3>
        <button className="btn-primary" onClick={handleSave} disabled={mutation.isPending}>
          {mutation.isPending ? "保存中..." : "提交修正"}
        </button>
      </div>
      <textarea
        className="editor-textarea"
        style={{ minHeight: 200, marginTop: 12 }}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      {parseError && <p className="error">{parseError}</p>}
      {mutation.isSuccess && <p style={{ color: "#16a34a", fontSize: 13 }}>修正已保存</p>}
      {mutation.isError && <p className="error">保存失败: {(mutation.error as Error).message}</p>}
    </div>
  );
}
