# Root Test Entrypoints Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add root-level verification commands that always use the repository virtualenv and update the main README to point to those commands.

**Architecture:** Use `package.json` in the repo root as the stable command surface for day-to-day verification. Backend and AI gateway scripts call the checked-in `.venv` explicitly so shell activation is no longer required. The root README becomes the canonical place that points users to those scripts.

**Tech Stack:** npm scripts, Python virtualenv, pytest, Vite, Docker Compose

---

## Chunk 1: Root Scripts

### Task 1: Add stable root entrypoints

**Files:**
- Modify: `package.json`

- [x] Add root `npm` scripts for backend tests, backend integration tests, AI gateway tests, frontend build, compose verification, and clause reindexing.
- [x] Ensure Python commands call `../.venv/bin/pytest` or `../.venv/bin/python` from the service directories.

## Chunk 2: User-Facing Docs

### Task 2: Point README at the new commands

**Files:**
- Modify: `README.md`

- [x] Replace direct backend and AI gateway pytest examples with root `npm run ...` commands.
- [x] Add a short note that these commands intentionally avoid depending on the active shell Python environment.

## Chunk 3: Verification

### Task 3: Prove the entrypoints resolve correctly

**Files:**
- Modify: none

- [x] Run `npm run test:backend -- --version`.
- [x] Run `npm run test:ai-gateway -- --version`.
- [x] Run `npm run build:frontend`.
- [x] Report any pre-existing environment issues separately from command resolution.
