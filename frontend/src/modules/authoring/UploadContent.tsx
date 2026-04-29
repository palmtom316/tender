import { useCallback, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { listFiles, uploadFile, type ProjectFile } from "../../lib/api";
import { useNavigation } from "../../lib/NavigationContext";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function UploadContent() {
  const { projectId } = useNavigation();
  const queryClient = useQueryClient();
  const [dragging, setDragging] = useState(false);

  const { data: files = [], isLoading } = useQuery({
    queryKey: ["files", projectId],
    queryFn: ({ signal }) => {
      if (!projectId) throw new Error("No project selected");
      return listFiles(projectId, { signal });
    },
    enabled: !!projectId,
  });

  const upload = useMutation({
    mutationFn: (file: File) => {
      if (!projectId) throw new Error("No project selected");
      return uploadFile(projectId, file);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["files", projectId] });
    },
  });

  const handleFiles = useCallback(
    (fileList: FileList | null) => {
      if (!fileList) return;
      Array.from(fileList).forEach((f) => upload.mutate(f));
    },
    [upload],
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      handleFiles(e.dataTransfer.files);
    },
    [handleFiles],
  );

  if (!projectId) {
    return (
      <div className="empty-state">
        <span className="empty-state__icon">项</span>
        <p className="empty-state__title">先选择投标项目</p>
        <p className="empty-state__description">选择项目后，可上传招标文件并启动解析流程。</p>
      </div>
    );
  }

  return (
    <div>
      <h1 className="section-heading">文件上传</h1>

      <div
        className={`drop-zone ${dragging ? "drop-zone--active" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => {
          const input = document.createElement("input");
          input.type = "file";
          input.multiple = true;
          input.accept = ".pdf,.doc,.docx";
          input.onchange = () => handleFiles(input.files);
          input.click();
        }}
      >
        <p className="drop-zone-text">
          {upload.isPending ? "上传中..." : "拖拽文件到此处，或点击选择文件"}
        </p>
        <p className="drop-zone-hint">支持 PDF、DOC、DOCX 格式</p>
      </div>

      {upload.isError && (
        <p className="text-error">上传失败: {(upload.error as Error).message}</p>
      )}

      <h2 className="section-heading section-heading--sm">已上传文件</h2>
      {isLoading ? (
        <div className="skeleton-stack" aria-label="文件列表加载中">
          <div className="skeleton-card" />
          <div className="skeleton-card" />
        </div>
      ) : files.length === 0 ? (
        <div className="empty-state">
          <span className="empty-state__icon">文</span>
          <p className="empty-state__title">还没有上传文件</p>
          <p className="empty-state__description">拖拽 PDF、DOC 或 DOCX 到上方区域，上传后会出现在这里。</p>
        </div>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>文件名</th>
              <th>类型</th>
              <th>大小</th>
              <th>上传时间</th>
            </tr>
          </thead>
          <tbody>
            {files.map((f: ProjectFile) => (
              <tr key={f.id}>
                <td>{f.filename}</td>
                <td>{f.content_type}</td>
                <td>{formatBytes(f.size_bytes)}</td>
                <td>{new Date(f.created_at).toLocaleString("zh-CN")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
