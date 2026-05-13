# Project Template Kind Date Format Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make new project classification match six tender template kinds, remove bid bond input, and display project dates as `YYYY/MM/DD`.

**Architecture:** Keep backend project schema unchanged; normalize the frontend create-project form to six stable template-kind values and stop sending bid bond fields. Add a small date formatting helper used by project cards. Keep database template packages untouched because only SGCC distribution packages currently exist.

**Tech Stack:** React 18, TypeScript, Vitest, existing project API.

---

### Task 1: Project form behavior
- Test `ProjectsModule` renders six template kinds, does not render guarantee/bid-bond input, preserves voltage level, and sends selected kind to `project_type/business_line/sub_type`.
- Implement constants and submit payload update.

### Task 2: Project date display
- Test dates render as `YYYY/MM/DD`.
- Implement shared formatter and use it in project cards.

### Task 3: Verify
- Run targeted frontend tests and build.
