import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Badge } from "../../components/ui/Badge";
import { ClayButton } from "../../components/ui/ClayButton";
import {
  confirmProjectPersonnelSelections,
  createProjectPersonnelSelection,
  deleteProjectPersonnelSelection,
  fetchLibraryCompanies,
  fetchProjectPersonnelPeople,
  fetchProjectPersonnelPreview,
  fetchProjectPersonnelSelections,
  updateProjectPersonnelSelection,
} from "../../lib/api";

type PersonnelSelectionWorkbenchProps = {
  projectId: string;
};

function selectionTitle(row: { snapshot_json: Record<string, unknown> | null; person_id: string }) {
  return String(row.snapshot_json?.full_name ?? row.person_id);
}

export function PersonnelSelectionWorkbench({ projectId }: PersonnelSelectionWorkbenchProps) {
  const queryClient = useQueryClient();
  const [libraryCompanyId, setLibraryCompanyId] = useState("");
  const [search, setSearch] = useState("");
  const [savingRoleId, setSavingRoleId] = useState("");

  const librariesQuery = useQuery({
    queryKey: ["library-companies"],
    queryFn: ({ signal }) => fetchLibraryCompanies({ signal }),
  });

  const candidatesQuery = useQuery({
    queryKey: ["personnel-people", projectId, libraryCompanyId, search],
    queryFn: ({ signal }) => fetchProjectPersonnelPeople({
      projectId,
      libraryCompanyId: libraryCompanyId || undefined,
      q: search,
      signal,
    }),
    enabled: !!projectId,
  });

  const selectionsQuery = useQuery({
    queryKey: ["personnel-selections", projectId],
    queryFn: ({ signal }) => fetchProjectPersonnelSelections(projectId, { signal }),
    enabled: !!projectId,
  });

  const previewQuery = useQuery({
    queryKey: ["personnel-preview", projectId],
    queryFn: ({ signal }) => fetchProjectPersonnelPreview(projectId, { signal }),
    enabled: !!projectId,
  });

  const createSelection = useMutation({
    mutationFn: (personId: string) => createProjectPersonnelSelection(projectId, { person_id: personId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["personnel-selections", projectId] });
    },
  });

  const deleteSelection = useMutation({
    mutationFn: (selectionId: string) => deleteProjectPersonnelSelection(projectId, selectionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["personnel-selections", projectId] });
      queryClient.invalidateQueries({ queryKey: ["personnel-preview", projectId] });
    },
  });

  const confirmSelections = useMutation({
    mutationFn: () => confirmProjectPersonnelSelections(projectId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["personnel-selections", projectId] });
      queryClient.invalidateQueries({ queryKey: ["personnel-preview", projectId] });
    },
  });

  const selectedByPersonId = useMemo(() => {
    const map = new Map<string, string>();
    for (const row of selectionsQuery.data ?? []) {
      map.set(row.person_id, row.id);
    }
    return map;
  }, [selectionsQuery.data]);

  const saveRole = async (selectionId: string, intendedRole: string) => {
    setSavingRoleId(selectionId);
    try {
      await updateProjectPersonnelSelection(projectId, selectionId, { intended_role: intendedRole || null });
      await queryClient.invalidateQueries({ queryKey: ["personnel-selections", projectId] });
    } finally {
      setSavingRoleId("");
    }
  };

  const selections = selectionsQuery.data ?? [];
  const previewRows = previewQuery.data ?? [];
  const previewColumns = previewRows[0] ? Object.keys(previewRows[0]) : [];

  return (
    <section className="equipment-workbench" aria-label="人员清单工作台">
      <div className="template-panel__header">
        <div>
          <div className="template-panel__eyebrow">Manual Selection</div>
          <h2>投标人员清单</h2>
          <p className="template-panel__description">从人员资料库选择项目团队成员，确认后冻结人员快照，供技术标人员表使用。模板锚点：{"{{personnel_table}}"}</p>
        </div>
        <ClayButton type="button" onClick={() => confirmSelections.mutate()} disabled={confirmSelections.isPending || selections.length === 0}>
          {confirmSelections.isPending ? "确认中..." : "确认并冻结快照"}
        </ClayButton>
      </div>

      <div className="asset-toolbar__filters personnel-selection-filters">
        <select className="clay-input" aria-label="按公司库筛选人员" value={libraryCompanyId} onChange={(event) => setLibraryCompanyId(event.target.value)}>
          <option value="">全部公司库</option>
          {(librariesQuery.data ?? []).map((row) => (
            <option key={row.id} value={row.id}>{row.company_name}</option>
          ))}
        </select>
        <input
          className="clay-input"
          aria-label="搜索人员资料"
          placeholder="搜索姓名、岗位、专业、职称、电话"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <div />
      </div>

      <div className="equipment-workbench__grid">
        <div className="equipment-workbench__panel">
          <div className="equipment-workbench__panel-header">
            <h3 className="panel-title-tight">候选人员</h3>
            <Badge variant="info">{candidatesQuery.data?.length ?? 0}</Badge>
          </div>
          <div className="stack-sm">
            {(candidatesQuery.data ?? []).map((person) => {
              const selectedId = selectedByPersonId.get(person.id);
              return (
                <div key={person.id} className="template-list__item">
                  <div className="equipment-workbench__item-head">
                    <strong>{person.full_name}</strong>
                    {person.role_name && <Badge>{person.role_name}</Badge>}
                  </div>
                  <span className="template-list__meta">
                    {[person.specialty, person.title, person.education, person.years_experience == null ? null : `${person.years_experience}年`].filter(Boolean).join(" / ") || "—"}
                  </span>
                  <div className="equipment-workbench__item-actions">
                    {selectedId ? (
                      <ClayButton type="button" variant="ghost" size="sm" onClick={() => deleteSelection.mutate(selectedId)} disabled={deleteSelection.isPending}>
                        移除
                      </ClayButton>
                    ) : (
                      <ClayButton type="button" size="sm" onClick={() => createSelection.mutate(person.id)} disabled={createSelection.isPending}>
                        加入
                      </ClayButton>
                    )}
                  </div>
                </div>
              );
            })}
            {!candidatesQuery.isLoading && (candidatesQuery.data?.length ?? 0) === 0 && (
              <div className="template-strip-empty">当前没有可选人员。</div>
            )}
          </div>
        </div>

        <div className="equipment-workbench__panel">
          <div className="equipment-workbench__panel-header">
            <h3 className="panel-title-tight">已选人员</h3>
            <Badge variant="primary">{selections.length}</Badge>
          </div>
          <div className="stack-sm">
            {selections.map((row) => (
              <div key={row.id} className="template-list__item">
                <div className="equipment-workbench__item-head">
                  <strong>{selectionTitle(row)}</strong>
                  {row.confirmed ? <Badge variant="success">已确认</Badge> : <Badge variant="warning">未确认</Badge>}
                </div>
                <input
                  className="clay-input"
                  aria-label="拟任岗位"
                  defaultValue={row.intended_role ?? String(row.snapshot_json?.role_name ?? "")}
                  placeholder="拟任岗位"
                  onBlur={(event) => void saveRole(row.id, event.target.value)}
                  disabled={savingRoleId === row.id}
                />
                <div className="equipment-workbench__item-actions">
                  <ClayButton type="button" variant="ghost" size="sm" onClick={() => deleteSelection.mutate(row.id)} disabled={deleteSelection.isPending}>
                    移除
                  </ClayButton>
                </div>
              </div>
            ))}
            {!selectionsQuery.isLoading && selections.length === 0 && (
              <div className="template-strip-empty">当前项目还没有已选人员。</div>
            )}
          </div>
        </div>
      </div>

      <div className="equipment-workbench__preview">
        <div className="equipment-workbench__panel-header">
          <h3 className="panel-title-tight">人员表预览</h3>
          <Badge variant="info">{previewRows.length}</Badge>
        </div>
        {previewRows.length === 0 ? (
          <div className="template-strip-empty">确认后可在这里预览技术标人员表。</div>
        ) : (
          <div className="asset-table-wrap">
            <table className="asset-table personnel-selection-preview-table">
              <thead>
                <tr>
                  {previewColumns.map((column) => (
                    <th key={column}>{column}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {previewRows.map((row, index) => (
                  <tr key={`personnel-${index}`}>
                    {previewColumns.map((column) => (
                      <td key={column}>{row[column]}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
