import { useState } from "react";

import { Card } from "../../../components/ui/Card";
import { ClayButton } from "../../../components/ui/ClayButton";
import { searchStandardClauses, type StandardSearchHit } from "../../../lib/api";

type StandardSearchCardProps = {
  onOpenHit: (hit: StandardSearchHit) => void;
};

export function StandardSearchCard({ onOpenHit }: StandardSearchCardProps) {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [results, setResults] = useState<StandardSearchHit[]>([]);

  const handleSearch = async () => {
    const trimmed = query.trim();
    if (!trimmed) {
      setResults([]);
      setError("请输入关键词");
      return;
    }

    setLoading(true);
    setError("");
    try {
      setResults(await searchStandardClauses(trimmed));
    } catch (err: unknown) {
      setResults([]);
      setError(err instanceof Error ? err.message : "查询失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="standard-search-card">
      <div className="standard-search-card__header">
        <div>
          <h2>规范规程查询</h2>
          <p>按关键词检索 AI 解析条款，并从命中位置直接进入 PDF 对照查阅。</p>
        </div>
        <div className="standard-search-card__controls">
          <input
            className="clay-input"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="输入关键词，如 混凝土、抗震、强度等级"
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                void handleSearch();
              }
            }}
          />
          <ClayButton type="button" onClick={() => void handleSearch()} disabled={loading}>
            {loading ? "查询中..." : "查询"}
          </ClayButton>
        </div>
      </div>

      {error && <div className="warning-banner">{error}</div>}

      {results.length === 0 ? (
        <div className="empty-state">输入关键词后，可在这里查看命中的规范条款。</div>
      ) : (
        <div className="standard-search-card__results">
          <table className="data-table">
            <thead>
              <tr>
                <th>规范名称</th>
                <th>专业</th>
                <th>条款号</th>
                <th>条款标签</th>
                <th>总结</th>
                <th>查阅</th>
              </tr>
            </thead>
            <tbody>
              {results.map((hit) => (
                <tr key={`${hit.standard_id}-${hit.clause_id}`}>
                  <td>{hit.standard_name}</td>
                  <td>{hit.specialty ?? "-"}</td>
                  <td>{hit.clause_no ?? "-"}</td>
                  <td>{hit.tags.join(" / ") || "-"}</td>
                  <td>{hit.summary ?? "-"}</td>
                  <td>
                    <ClayButton type="button" variant="secondary" size="sm" onClick={() => onOpenHit(hit)}>
                      查阅
                    </ClayButton>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
