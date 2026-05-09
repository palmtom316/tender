# 偏差表功能使用说明

## 功能概述

偏差表功能允许用户交互式地填写商务偏差表和技术偏差表。默认情况下显示"无偏差"，用户可以根据需要添加偏差项。

## 后端实现

### 1. 数据存储
偏差表数据存储在 `bid_chapter` 表的 `metadata_json` 字段中，格式如下：

```json
{
  "deviation_table": {
    "has_deviation": false,
    "items": []
  }
}
```

### 2. API端点

- `GET /api/bid-outline/chapters/{chapter_id}/deviation-table` - 获取偏差表数据
- `PUT /api/bid-outline/chapters/{chapter_id}/deviation-table` - 更新偏差表数据

### 3. 文档生成

在生成DOCX文档时，系统会检查章节的 `metadata_json` 中是否有 `deviation_table` 数据：
- 如果有，则渲染成表格
- 如果没有，则使用章节的 markdown 内容

表格格式：
- 标题：章节标题（如"商务偏差表"或"技术偏差表"）
- 列：序号、采购文件条目号、采购文件条款、应答文件条款、偏差说明
- 默认行：1 | 采购文件全部条目号 | 采购文件全部条款 | 应答文件全部条款 | 无偏差
- 第二行："以下无正文"
- 如果有偏差项，则在后续行显示
- 表格下方显示声明文字

## 前端实现

### 1. 组件

`DeviationTableEditor` 组件提供交互式编辑界面：
- 显示章节标题
- 复选框切换"有偏差"状态
- 添加/删除偏差项
- 编辑偏差项的各个字段
- 保存按钮

### 2. 集成到编辑器

在 `EditorContent.tsx` 中集成偏差表编辑器的示例代码：

```tsx
import { DeviationTableEditor } from "../../components/DeviationTableEditor";
import { fetchDeviationTable, updateDeviationTable } from "../../lib/api";

// 在组件中添加状态
const [editingDeviationChapterId, setEditingDeviationChapterId] = useState<string | null>(null);

// 添加查询
const { data: deviationData } = useQuery({
  queryKey: ["deviation-table", editingDeviationChapterId],
  queryFn: ({ signal }) => {
    if (!editingDeviationChapterId) throw new Error("No chapter selected");
    return fetchDeviationTable(editingDeviationChapterId, { signal });
  },
  enabled: !!editingDeviationChapterId,
});

// 添加保存mutation
const saveDeviation = useMutation({
  mutationFn: ({ chapterId, data }: { chapterId: string; data: DeviationTableData }) =>
    updateDeviationTable(chapterId, data),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ["deviation-table"] });
  },
});

// 在章节列表中添加"编辑偏差表"按钮
{outline?.chapters
  .filter(ch => ch.chapter_title.includes("偏差表"))
  .map((chapter) => (
    <div key={chapter.id} className="outline-item">
      <span className="outline-code">{chapter.chapter_code}</span>
      <span>{chapter.chapter_title}</span>
      <ClayButton
        size="sm"
        onClick={() => setEditingDeviationChapterId(chapter.id)}
      >
        编辑偏差表
      </ClayButton>
    </div>
  ))}

// 在编辑区域显示偏差表编辑器
{editingDeviationChapterId && deviationData && (
  <DeviationTableEditor
    chapterId={editingDeviationChapterId}
    chapterTitle={outline?.chapters.find(ch => ch.id === editingDeviationChapterId)?.chapter_title || ""}
    initialData={deviationData}
    onSave={(data) => saveDeviation.mutateAsync({ chapterId: editingDeviationChapterId, data })}
  />
)}
```

## 使用流程

1. 用户在编辑器中找到"商务偏差表"或"技术偏差表"章节
2. 点击"编辑偏差表"按钮
3. 默认显示"无偏差"状态
4. 如果需要添加偏差：
   - 勾选"有偏差"复选框
   - 点击"添加偏差项"按钮
   - 填写偏差项的各个字段
   - 可以添加多个偏差项
   - 点击"保存"按钮
5. 生成文档时，偏差表会自动渲染成表格格式

## 注意事项

- 偏差表章节的 `chapter_code` 为 "1"（商务偏差表和技术偏差表都是）
- 可以通过 `chapter_title` 来区分是商务偏差表还是技术偏差表
- 偏差项的序号从2开始（因为1是默认的"无偏差"行）
- 保存后需要重新生成文档才能看到更新后的偏差表
