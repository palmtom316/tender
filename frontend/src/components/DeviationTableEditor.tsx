import { useState, useEffect } from "react";
import { ClayButton } from "./ui/ClayButton";
import "./DeviationTableEditor.css";

export interface DeviationItem {
  seq_number: number;
  procurement_clause_number: string;
  procurement_clause: string;
  response_clause: string;
  deviation_note: string;
}

export interface DeviationTableData {
  has_deviation: boolean;
  items: DeviationItem[];
}

interface DeviationTableEditorProps {
  chapterId: string;
  chapterTitle: string;
  initialData?: DeviationTableData;
  onSave: (data: DeviationTableData) => Promise<void>;
}

export function DeviationTableEditor({
  chapterId,
  chapterTitle,
  initialData,
  onSave,
}: DeviationTableEditorProps) {
  const [hasDeviation, setHasDeviation] = useState(initialData?.has_deviation ?? false);
  const [items, setItems] = useState<DeviationItem[]>(initialData?.items ?? []);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (initialData) {
      setHasDeviation(initialData.has_deviation);
      setItems(initialData.items);
    }
  }, [initialData]);

  const addDeviationItem = () => {
    const newItem: DeviationItem = {
      seq_number: items.length + 2, // Start from 2 because 1 is the default "no deviation" row
      procurement_clause_number: "",
      procurement_clause: "",
      response_clause: "",
      deviation_note: "",
    };
    setItems([...items, newItem]);
    setHasDeviation(true);
  };

  const removeDeviationItem = (index: number) => {
    const newItems = items.filter((_, i) => i !== index);
    setItems(newItems);
    if (newItems.length === 0) {
      setHasDeviation(false);
    }
  };

  const updateDeviationItem = (index: number, field: keyof DeviationItem, value: string | number) => {
    const newItems = [...items];
    newItems[index] = { ...newItems[index], [field]: value };
    setItems(newItems);
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await onSave({ has_deviation: hasDeviation, items });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="deviation-table-editor">
      <div className="deviation-table-editor__header">
        <h3>{chapterTitle}</h3>
        <div className="deviation-table-editor__actions">
          <ClayButton
            size="sm"
            variant="secondary"
            onClick={addDeviationItem}
          >
            添加偏差项
          </ClayButton>
          <ClayButton
            size="sm"
            onClick={handleSave}
            disabled={isSaving}
          >
            {isSaving ? "保存中..." : "保存"}
          </ClayButton>
        </div>
      </div>

      <div className="deviation-table-editor__status">
        <label>
          <input
            type="checkbox"
            checked={hasDeviation}
            onChange={(e) => {
              setHasDeviation(e.target.checked);
              if (!e.target.checked) {
                setItems([]);
              }
            }}
          />
          <span>有偏差</span>
        </label>
      </div>

      {!hasDeviation && (
        <div className="deviation-table-editor__no-deviation">
          <p>默认状态：无偏差</p>
          <p className="text-muted">
            文档将显示"采购文件全部条目号 / 采购文件全部条款 / 应答文件全部条款 / 无偏差"
          </p>
        </div>
      )}

      {hasDeviation && items.length > 0 && (
        <div className="deviation-table-editor__table">
          <table>
            <thead>
              <tr>
                <th style={{ width: "60px" }}>序号</th>
                <th style={{ width: "150px" }}>采购文件条目号</th>
                <th style={{ width: "200px" }}>采购文件条款</th>
                <th style={{ width: "200px" }}>应答文件条款</th>
                <th style={{ width: "200px" }}>偏差说明</th>
                <th style={{ width: "80px" }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, index) => (
                <tr key={index}>
                  <td>
                    <input
                      type="number"
                      value={item.seq_number}
                      onChange={(e) =>
                        updateDeviationItem(index, "seq_number", parseInt(e.target.value) || 0)
                      }
                      className="clay-input deviation-table-editor__field"
                    />
                  </td>
                  <td>
                    <input
                      type="text"
                      value={item.procurement_clause_number}
                      onChange={(e) =>
                        updateDeviationItem(index, "procurement_clause_number", e.target.value)
                      }
                      className="clay-input deviation-table-editor__field"
                      placeholder="条目号"
                    />
                  </td>
                  <td>
                    <textarea
                      value={item.procurement_clause}
                      onChange={(e) =>
                        updateDeviationItem(index, "procurement_clause", e.target.value)
                      }
                      className="clay-textarea deviation-table-editor__field deviation-table-editor__field--textarea"
                      placeholder="采购文件条款"
                      rows={2}
                    />
                  </td>
                  <td>
                    <textarea
                      value={item.response_clause}
                      onChange={(e) =>
                        updateDeviationItem(index, "response_clause", e.target.value)
                      }
                      className="clay-textarea deviation-table-editor__field deviation-table-editor__field--textarea"
                      placeholder="应答文件条款"
                      rows={2}
                    />
                  </td>
                  <td>
                    <textarea
                      value={item.deviation_note}
                      onChange={(e) =>
                        updateDeviationItem(index, "deviation_note", e.target.value)
                      }
                      className="clay-textarea deviation-table-editor__field deviation-table-editor__field--textarea"
                      placeholder="偏差说明"
                      rows={2}
                    />
                  </td>
                  <td>
                    <ClayButton
                      size="sm"
                      variant="danger"
                      onClick={() => removeDeviationItem(index)}
                    >
                      删除
                    </ClayButton>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="deviation-table-editor__footer">
        <p className="text-muted">
          应答人声明：针对本采购标的，除本表已列明偏差外，我们接受采购文件规定的其余全部技术条件，
          并承诺按照采购文件规定的技术条件提供对应产品和服务。
        </p>
      </div>
    </div>
  );
}
