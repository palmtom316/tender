# Business Assembly MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a usable商务/资格章节“资料编排” workflow in Authoring so tender engineers can select a chapter, inspect required material slots, browse candidate materials on the right, and bind a candidate to the current slot without needing template-maintenance concepts.

**Architecture:** Keep the current `EditorContent` page and extend it rather than creating a new route. Use deterministic frontend rules to derive material slots and candidate domains for `qualification` / `business` chapters from existing outline chapter data plus `assembleBusinessBid()` missing-material signals. Persist nothing in phase 1 beyond in-memory UI state; this creates a safe, testable interaction loop without expanding backend scope prematurely.

**Tech Stack:** React 19 + TypeScript, TanStack Query, Vitest + Testing Library.

---

## File Structure

- Modify: `frontend/src/modules/authoring/EditorContent.tsx`
  - Add selected material slot state, candidate binding state, right-side candidate panel, and business-chapter-only workflow.
- Modify: `frontend/src/modules/authoring/chapterDelivery.ts`
  - Upgrade material-slot generation and add deterministic candidate-domain inference.
- Create: `frontend/src/modules/authoring/businessMaterialWorkbench.ts`
  - Centralize business chapter → slot rules and candidate generation helpers.
- Test: `frontend/src/modules/authoring/EditorContent.test.tsx`
  - Add UI workflow regression tests for slot selection, candidate visibility, and binding state transition.

---

### Task 1: Define deterministic business material workbench helpers

**Files:**
- Create: `frontend/src/modules/authoring/businessMaterialWorkbench.ts`
- Modify: `frontend/src/modules/authoring/chapterDelivery.ts`
- Test: `frontend/src/modules/authoring/EditorContent.test.tsx`

- [ ] **Step 1: Write the failing test for right-side candidate panel content**

Add a new test in `frontend/src/modules/authoring/EditorContent.test.tsx` asserting that for a business chapter with missing certificate material, selecting the chapter shows candidate groups like “公司资料候选” and “证照/附件候选”, and the target slot can be highlighted.

```tsx
it("shows candidate material groups for a selected business material slot", async () => {
  fetchBidOutlineMock.mockResolvedValueOnce({
    id: "outline-1",
    project_id: "proj-1",
    outline_name: "默认目录",
    status: "confirmed",
    chapters: [
      {
        id: "chapter-business-1",
        project_id: "proj-1",
        outline_id: "outline-1",
        chapter_code: "3",
        chapter_title: "企业资信情况",
        volume_type: "business",
        sort_order: 1,
        metadata_json: {},
      },
    ],
  });
  fetchDraftsMock.mockResolvedValueOnce([]);
  assembleBusinessBidMock.mockResolvedValueOnce({
    project_id: "proj-1",
    run: {},
    chapters: [],
    response_matrix: [],
    missing_materials: [
      { chapter_code: "3", material_name: "安全生产许可证", material_type: "certificate", reason: "缺少有效附件" },
    ],
    boundary: "商务资料装配完成，仍有缺失资料。",
  });

  render(withClient(<EditorContent />));
  fireEvent.click(await screen.findByRole("button", { name: "资格商务装配" }));
  await waitFor(() => expect(assembleBusinessBidMock).toHaveBeenCalled());
  fireEvent.click((await screen.findAllByText("3"))[1]);
  fireEvent.click(await screen.findByRole("button", { name: "选择资料位 安全生产许可证" }));

  expect(await screen.findByText("当前资料位：安全生产许可证")).toBeInTheDocument();
  expect(screen.getByText("公司资料候选")).toBeInTheDocument();
  expect(screen.getByText("证照/附件候选")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd /home/palmtom/projects/tender
.venv/bin/pytest frontend/src/modules/authoring/EditorContent.test.tsx -q
```

Expected: FAIL because the UI does not yet render candidate material groups or slot-selection actions.

- [ ] **Step 3: Implement deterministic slot/candidate helpers**

Create `frontend/src/modules/authoring/businessMaterialWorkbench.ts` with typed helpers for:
- chapter-to-slot defaults,
- slot source domain inference,
- deterministic candidate groups.

Core shapes:

```ts
export interface BusinessMaterialCandidate {
  key: string;
  label: string;
  groupLabel: string;
  sourceLabel: string;
  summary: string;
}

export function buildBusinessMaterialCandidates(slot: MaterialSlotSummary, chapterTitle: string): BusinessMaterialCandidate[] {
  // deterministic groups only; no backend persistence yet
}
```

Update `chapterDelivery.ts` to import and use shared inference functions instead of embedding all logic inline.

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
cd /home/palmtom/projects/tender
.venv/bin/pytest frontend/src/modules/authoring/EditorContent.test.tsx -q
```

Expected: PASS for the new candidate-panel test.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/modules/authoring/businessMaterialWorkbench.ts frontend/src/modules/authoring/chapterDelivery.ts frontend/src/modules/authoring/EditorContent.test.tsx
git commit -m "feat: add business material candidate helpers"
```

---

### Task 2: Add slot selection and right-side candidate panel in EditorContent

**Files:**
- Modify: `frontend/src/modules/authoring/EditorContent.tsx`
- Test: `frontend/src/modules/authoring/EditorContent.test.tsx`

- [ ] **Step 1: Write the failing test for slot binding interaction**

Add a test asserting that clicking a candidate changes the slot state from missing to bound in the UI.

```tsx
it("binds a candidate material to the selected slot in the business workbench", async () => {
  fetchBidOutlineMock.mockResolvedValueOnce({
    id: "outline-1",
    project_id: "proj-1",
    outline_name: "默认目录",
    status: "confirmed",
    chapters: [
      {
        id: "chapter-business-1",
        project_id: "proj-1",
        outline_id: "outline-1",
        chapter_code: "3",
        chapter_title: "企业资信情况",
        volume_type: "business",
        sort_order: 1,
        metadata_json: {},
      },
    ],
  });
  fetchDraftsMock.mockResolvedValueOnce([]);
  assembleBusinessBidMock.mockResolvedValueOnce({
    project_id: "proj-1",
    run: {},
    chapters: [],
    response_matrix: [],
    missing_materials: [
      { chapter_code: "3", material_name: "安全生产许可证", material_type: "certificate", reason: "缺少有效附件" },
    ],
    boundary: "商务资料装配完成，仍有缺失资料。",
  });

  render(withClient(<EditorContent />));
  fireEvent.click(await screen.findByRole("button", { name: "资格商务装配" }));
  await waitFor(() => expect(assembleBusinessBidMock).toHaveBeenCalled());
  fireEvent.click((await screen.findAllByText("3"))[1]);
  fireEvent.click(await screen.findByRole("button", { name: "选择资料位 安全生产许可证" }));
  fireEvent.click(await screen.findByRole("button", { name: /绑定到当前资料位/i }));

  expect(await screen.findByText("已绑定资料")).toBeInTheDocument();
  expect(screen.getByText("已匹配")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
cd /home/palmtom/projects/tender
.venv/bin/pytest frontend/src/modules/authoring/EditorContent.test.tsx -q
```

Expected: FAIL because slot selection and binding state do not exist.

- [ ] **Step 3: Implement minimal UI state and candidate panel**

In `frontend/src/modules/authoring/EditorContent.tsx`:
- add `selectedMaterialSlotKeyByChapterId` state,
- add `boundMaterialByChapterId` state,
- render slot rows as buttons with labels `选择资料位 <slot.label>`,
- render a right-side panel titled `资料候选区`,
- show current selected slot label,
- allow binding first candidate with button label `绑定到当前资料位 <candidate.label>`.

Minimal rendering contract:

```tsx
<section className="chapter-delivery-card" aria-label="资料候选区">
  <div className="chapter-delivery-card__header">
    <div>
      <strong>资料候选区</strong>
      <p>按资料来源筛选候选资料，并绑定到当前资料位。</p>
    </div>
  </div>
</section>
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
cd /home/palmtom/projects/tender
.venv/bin/pytest frontend/src/modules/authoring/EditorContent.test.tsx -q
```

Expected: PASS for the new slot-binding test and previous tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/modules/authoring/EditorContent.tsx frontend/src/modules/authoring/EditorContent.test.tsx
git commit -m "feat: add business material binding panel"
```

---

### Task 3: Refine business-only visibility and preserve technical flow

**Files:**
- Modify: `frontend/src/modules/authoring/EditorContent.tsx`
- Test: `frontend/src/modules/authoring/EditorContent.test.tsx`

- [ ] **Step 1: Write the failing regression test for technical chapters**

Add a regression test ensuring the new candidate panel does not replace technical chapter cards.

```tsx
it("keeps technical chapters on AI content flow without business candidate panel", async () => {
  render(withClient(<EditorContent />));
  fireEvent.click((await screen.findAllByText("10.1"))[1]);

  expect(await screen.findByLabelText("图表任务")).toBeInTheDocument();
  expect(screen.queryByLabelText("资料候选区")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run the test to verify it fails if candidate panel leaks into technical chapters**

Run:

```bash
cd /home/palmtom/projects/tender
.venv/bin/pytest frontend/src/modules/authoring/EditorContent.test.tsx -q
```

Expected: FAIL if the candidate panel is not gated to `qualification` / `business` chapters only.

- [ ] **Step 3: Implement visibility guard**

In `EditorContent.tsx`, gate the business workbench by:

```ts
const isBusinessCompositionChapter = selectedOutlineChapter?.volume_type === "business" || selectedOutlineChapter?.volume_type === "qualification";
```

Only render candidate panel and slot selection controls when `isBusinessCompositionChapter` is true.

- [ ] **Step 4: Run the test suite to verify it passes**

Run:

```bash
cd /home/palmtom/projects/tender
.venv/bin/pytest frontend/src/modules/authoring/EditorContent.test.tsx -q
```

Expected: PASS for all EditorContent tests.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/modules/authoring/EditorContent.tsx frontend/src/modules/authoring/EditorContent.test.tsx
git commit -m "fix: limit business assembly workbench to business chapters"
```

---

### Task 4: Final verification

**Files:**
- Modify: none
- Test: `frontend/src/modules/authoring/EditorContent.test.tsx`

- [ ] **Step 1: Run the focused test suite**

Run:

```bash
cd /home/palmtom/projects/tender
.venv/bin/pytest frontend/src/modules/authoring/EditorContent.test.tsx -q
```

Expected: all tests PASS.

- [ ] **Step 2: Run the frontend unit subset if available in repo workflow**

Run:

```bash
cd /home/palmtom/projects/tender/frontend
npm test -- --run EditorContent.test.tsx
```

Expected: PASS or repo-standard equivalent for the file.

- [ ] **Step 3: Manual smoke check**

Run the app and verify:
- business chapter shows `资料位清单` + `资料候选区`;
- selecting a slot updates the right panel;
- binding updates slot status to `已匹配`;
- technical chapter still shows `AI 正文` + `图表任务`.

- [ ] **Step 4: Commit verification-only changes if any**

```bash
git status
```

Expected: no unexpected modified files.

