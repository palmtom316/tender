# Audit Report — Tender Frontend

**Date**: 2026-04-29
**Branch**: bid-template-packages

---

## Anti-Patterns Verdict

**PASS** — This does NOT look AI-generated. The warm earth-tone palette (clay/terracotta), custom inline SVG icon set, and tactile "clay button" aesthetic are distinctive and intentional. There's a coherent design language here. That said, some mild tells exist: the generic "Helvetica Neue" font stack, the stat-card pattern with oversized numbers, and scattered inline styles that undermine the token system. The overall impression is "bespoke but underbaked" rather than "AI slop."

---

## Audit Health Score

| # | Dimension | Score | Key Finding |
|---|-----------|-------|-------------|
| 1 | Accessibility | 1/4 | No ARIA labels, no focus indicators, missing form labels |
| 2 | Performance | 2/4 | 5/6 modules eagerly loaded, no image optimization |
| 3 | Theming | 2/4 | Token system exists but 30+ hard-coded colors; no dark mode |
| 4 | Responsive Design | 3/4 | Good breakpoints but 3 touch targets < 44px |
| 5 | Anti-Patterns | 3/4 | Distinctive clay aesthetic; mild issues with inline styles |
| **Total** | | **11/20** | **Acceptable** |

---

## Executive Summary

- **Audit Health Score**: 11/20 (Acceptable — significant work needed)
- **Total issues found**: 23 (4 P0, 8 P1, 7 P2, 4 P3)
- **Top critical issues**:
  1. Zero ARIA labels or landmark structure — screen reader users cannot navigate
  2. No dark mode support — hard-coded colors make it impossible to add later
  3. 3 interactive elements below 44×44px minimum touch target
  4. Inline styles in 10+ locations break the design token system
- **Recommended next steps**: Accessibility first (P0), then theming cleanup (P0), then responsive touch targets (P1), then performance (P2).

---

## Detailed Findings by Severity

### P0 — Blocking

**[P0] No ARIA labels, roles, or landmark structure**
- **Location**: All components (`Sidebar.tsx`, `WorkspaceTabs.tsx`, `CopilotPanel.tsx`, `AppShell.tsx`, etc.)
- **Category**: Accessibility
- **Impact**: Screen reader users cannot identify page regions, navigate between sections, or understand what interactive elements do. WCAG 2.1 Level A violation (1.3.1, 4.1.2).
- **WCAG**: 1.3.1 Info and Relationships, 4.1.2 Name Role Value
- **Recommendation**: Add `<main>` landmark to workspace content, `aria-label` to `<nav>`, `aria-current="page"` to active sidebar items, `aria-label` to icon-only buttons (sidebar toggle, copilot close), `role="log"` and `aria-live="polite"` to copilot message list.
- **Suggested command**: `/harden`

**[P0] No focus indicators defined**
- **Location**: `reset.css`, all interactive components
- **Category**: Accessibility
- **Impact**: Keyboard-only users cannot tell which element is focused. WCAG 2.1 Level AA violation (2.4.7 Focus Visible).
- **WCAG**: 2.4.7 Focus Visible
- **Recommendation**: Add `:focus-visible` outlines to all interactive elements in the design system. Never suppress outlines without providing a visible alternative.
- **Suggested command**: `/harden`

**[P0] No dark mode support + 30+ hard-coded color values**
- **Location**: `utilities.css` (lines 371-389 progress gradients, lines 401, 414-415 modal), `buttons.css:78` (danger hover), `ErrorBoundary.tsx:28-38`
- **Category**: Theming
- **Impact**: Dark mode cannot be implemented without rewriting large portions of CSS. Users with light sensitivity or who work in low-light environments have no alternative.
- **Recommendation**: Convert all hard-coded colors to CSS custom properties. Add `prefers-color-scheme: dark` media query block with a dark palette. The token system in `tokens.css` is well-structured — extend it.
- **Suggested command**: `/harden`

**[P0] No skip-to-content link**
- **Location**: Missing from `index.html` / `AppShell.tsx`
- **Category**: Accessibility
- **Impact**: Keyboard users must tab through every sidebar item (potentially 6+) to reach main content. WCAG 2.1 Level A violation (2.4.1 Bypass Blocks).
- **WCAG**: 2.4.1 Bypass Blocks
- **Recommendation**: Add a visually hidden "跳到主要内容" link as the first focusable element in the DOM.
- **Suggested command**: `/harden`

### P1 — Major

**[P1] Touch targets below 44×44px minimum**
- **Location**: `sidebar.css:18-24` (sidebar toggle 32×32px), `copilot.css:60-69` (close button 28×28px), `copilot.css:2-21` (trigger tab 24×64px)
- **Category**: Responsive Design
- **Impact**: Difficult or impossible to tap accurately on mobile/touch devices. WCAG 2.5.5 Target Size (AAA) / 2.5.8 (AA).
- **WCAG**: 2.5.8 Target Size (Minimum)
- **Recommendation**: Enlarge to at least 44×44px. The sidebar toggle and copilot close can use padding to expand hit area without changing visual size. The copilot trigger at 24px wide is particularly problematic.
- **Suggested command**: `/adapt`

**[P1] Copilot chat input has no accessible label**
- **Location**: `CopilotPanel.tsx:83-88`
- **Category**: Accessibility
- **Impact**: Screen reader users cannot identify the chat input field. WCAG 1.3.1, 3.3.2.
- **WCAG**: 1.3.1, 3.3.2 Labels or Instructions
- **Recommendation**: Add a `<label>` with `className="sr-only"` or use `aria-label="输入问题"`. The placeholder alone is insufficient.
- **Suggested command**: `/harden`

**[P1] File upload inputs have no accessible labels**
- **Location**: `DatabaseModule.tsx:153-161` (standard upload picker), `DatabaseModule.tsx:622` (company file), `DatabaseModule.tsx:789` (personnel file)
- **Category**: Accessibility
- **Impact**: Screen reader users cannot identify what file they're being asked to upload.
- **WCAG**: 1.3.1, 3.3.2
- **Recommendation**: Each file input needs an associated `<label>` or `aria-label`. The visually-hidden input inside `standard-upload-picker` has no accessible name.
- **Suggested command**: `/harden`

**[P1] Marquee has no pause/reduce-motion support**
- **Location**: `marquee.css:21` (continuous animation), `NotificationMarquee.tsx`
- **Category**: Accessibility
- **Impact**: Auto-scrolling content can trigger vestibular disorders. WCAG 2.2.2 Pause Stop Hide.
- **WCAG**: 2.2.2 Pause Stop Hide
- **Recommendation**: Add `@media (prefers-reduced-motion: reduce)` to disable animation. Add a pause button visible on focus. The existing `:hover` pause is insufficient for keyboard users.
- **Suggested command**: `/animate` or `/quieter`

**[P1] Hard-coded color `#B04D43` for danger button hover breaks token consistency**
- **Location**: `buttons.css:78`
- **Category**: Theming
- **Impact**: Cannot be themed, will not adapt to dark mode, diverges from the token system the rest of the design uses.
- **Recommendation**: Replace with a `--color-danger-hover` token, or compute via relative color if browser support allows.
- **Suggested command**: `/normalize`

**[P1] ErrorBoundary uses hard-coded colors**
- **Location**: `ErrorBoundary.tsx:28-38`
- **Category**: Theming
- **Impact**: Error state is un-themed, looks inconsistent with the rest of the app, won't work in dark mode.
- **Recommendation**: Use CSS classes from the design system (`clay-btn`, etc.) instead of inline styles with hard-coded `#666`, `#ccc`, `#f5f5f5`.
- **Suggested command**: `/normalize`

**[P1] 5 of 6 route modules load eagerly**
- **Location**: `ModuleRouter.tsx:4-8` (static imports for Projects, Authoring, Review, Export, Settings)
- **Category**: Performance
- **Impact**: Users download code for all modules on initial load, even if they only use one. Increases bundle size and TTI.
- **Recommendation**: Convert all module imports to `lazy()` — only DatabaseModule uses it currently.
- **Suggested command**: `/optimize`

**[P1] DatabaseModule polling has no cleanup guard against stale state**
- **Location**: `DatabaseModule.tsx:263-277`
- **Category**: Performance
- **Impact**: If the component unmounts and remounts quickly, old polling intervals could continue firing. The `standards` dependency in the effect array also causes the interval to be recreated on every standards change, defeating the purpose of the cleanup.
- **Recommendation**: Use a `useRef` to track the latest callback, or restructure to avoid `standards` in the dependency array.
- **Suggested command**: `/optimize`

### P2 — Minor

**[P2] No `<main>` landmark**
- **Location**: `AppShell.tsx:17` (`.workspace-content` is a plain `<div>`)
- **Category**: Accessibility
- **Impact**: Screen readers cannot quickly jump to main content.
- **WCAG**: 1.3.1
- **Recommendation**: Change `.workspace-content` from `<div>` to `<main>`.
- **Suggested command**: `/harden`

**[P2] Generic font stack "Helvetica Neue"**
- **Location**: `tokens.css:64`
- **Category**: Anti-Pattern
- **Impact**: Helvetica is the most generic sans-serif choice possible. The warm, tactile clay aesthetic deserves a more distinctive typeface. Chinese fonts (PingFang SC, Noto Sans SC) are fine but the Latin font choice undermines the design's character.
- **Recommendation**: Consider a distinctive serif or humanist sans for headings to complement the earthy/tactile aesthetic. Even just pairing a display font for headings would elevate the design significantly.
- **Suggested command**: `/typeset`

**[P2] Inline styles break token system in 15+ locations**
- **Location**: `DatabaseModule.tsx` (multiple `style={{...}}` with hard-coded CSS var references), `Sidebar.tsx:86`, `ErrorBoundary.tsx:26-42`
- **Category**: Theming / Anti-Pattern
- **Impact**: Inline styles cannot be overridden by CSS, cannot respond to media queries or theme changes, and mix implementation details into component logic.
- **Recommendation**: Extract inline styles into CSS classes. The DatabaseModule particularly has extensive inline grids that duplicate the layout patterns already in utilities.css.
- **Suggested command**: `/extract`

**[P2] Stat card pattern with oversized number**
- **Location**: `cards.css:28-44` (`.stat-card`, `.stat-value` at 36px)
- **Category**: Anti-Pattern
- **Impact**: The "hero metric" pattern (giant number + small label) is a common AI-generation tell. Used sparingly it's fine, but the 36px font for a stat value in a product that isn't a dashboard is unusual.
- **Recommendation**: If not actively used, remove. If used, reduce the font size and integrate more naturally into card layouts.
- **Suggested command**: `/distill`

**[P2] No reduced motion media query anywhere**
- **Location**: All CSS files with animations (`marquee.css:21`, `utilities.css:51`, `buttons.css`, `copilot.css`)
- **Category**: Accessibility
- **Impact**: Users who prefer reduced motion get no relief from animations and transitions.
- **WCAG**: 2.3.3 Animation from Interactions
- **Recommendation**: Add `@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; } }` to reset.css.
- **Suggested command**: `/harden`

**[P2] Upload table 6-column grid has no mobile fallback**
- **Location**: `utilities.css:957-961` (`.standard-upload-row`)
- **Category**: Responsive Design
- **Impact**: On narrow screens (<600px), 6 columns of form inputs become unusable.
- **Recommendation**: Add a breakpoint that stacks the upload form fields vertically on mobile.
- **Suggested command**: `/adapt`

**[P2] Search input in StandardSearchCard lacks clear button**
- **Location**: `StandardSearchCard.tsx`
- **Category**: Accessibility
- **Impact**: Users cannot easily clear search text without selecting and deleting.
- **Recommendation**: Add a clear/X button inside or adjacent to the search input that appears when text is present.
- **Suggested command**: `/clarify`

### P3 — Polish

**[P3] Empty states are minimal text with no illustration or action**
- **Location**: `utilities.css:72-77` (`.empty-state`), `DatabaseModule.tsx:211-214, 862-870`
- **Category**: Anti-Pattern
- **Impact**: Empty states feel abandoned rather than deliberately designed. First-time users see "此模块正在开发中" with no guidance.
- **Recommendation**: Add a brief description of what will appear here, or a call-to-action to get started.
- **Suggested command**: `/onboard`

**[P3] No loading skeleton — only spinner**
- **Location**: `utilities.css:45-63` (`.spinner`), used throughout
- **Category**: Anti-Pattern / Performance
- **Impact**: Spinners are generic and feel slow. Skeleton screens reduce perceived wait time and provide layout stability.
- **Recommendation**: Add a simple skeleton card component for the standards table and card grids.
- **Suggested command**: `/delight`

**[P3] Spinner animation uses `transform: rotate(360deg)` without `will-change`**
- **Location**: `utilities.css:51-57`
- **Category**: Performance
- **Impact**: Minimal in practice for a small element, but best practice for any continuous animation.
- **Recommendation**: Add `will-change: transform` to `.spinner`.
- **Suggested command**: `/optimize`

**[P3] Error state uses `window.confirm()` for destructive action**
- **Location**: `DatabaseModule.tsx:364`
- **Category**: Anti-Pattern
- **Impact**: `window.confirm()` is unstyled, non-localized, and looks unprofessional. It also blocks the main thread.
- **Recommendation**: Build or use a custom confirmation dialog component styled to match the design system.
- **Suggested command**: `/polish`

---

## Patterns & Systemic Issues

- **Hard-coded colors in 30+ locations** — `utilities.css` alone has 15+ hard-coded hex/rgba values for progress bars, modals, code blocks, tree items, and shadows. These bypass the otherwise well-structured token system in `tokens.css`.
- **No ARIA in the entire app** — Not a single `aria-label`, `aria-current`, `aria-live`, or `role` attribute exists beyond implicit HTML semantics. This is a systemic gap, not a one-off.
- **Inline styles proliferating** — `DatabaseModule.tsx` uses `style={{...}}` extensively, often with references to CSS custom properties (which works but prevents media query overrides and dark mode).
- **Only 1/6 route modules lazy-loaded** — Despite having `React.lazy` available and already using it for DatabaseModule, the other 5 modules import eagerly.

---

## Positive Findings

1. **Cohesive design token system** (`tokens.css`) — Well-organized, semantic naming, covers colors, spacing, typography, shadows, radii, transitions. This is the foundation to build on.
2. **Custom inline SVG icon set** — No icon library dependency. Icons are typed, lightweight, and use `currentColor` for theming. Excellent approach.
3. **Responsive grid patterns** — Consistent use of `minmax()`, `auto-fill`, `min()`, and `clamp()` throughout. The sidebar off-canvas pattern on mobile is correct.
4. **Proper AbortController usage** — Fetch requests are properly cleaned up on unmount and on subsequent requests (race condition handling in viewer).
5. **CSS animations use compositor-only properties** — Transitions and animations use `transform` and `opacity` correctly, avoiding layout thrashing.
6. **`lang="zh-CN"` on `<html>`** — Correct and helpful for screen readers and translation tools.
7. **Distinctive clay aesthetic** — The warm earth-tones, tactile shadows, and organic feel are memorable and differentiated. This is not generic AI-generated design.

---

## Recommended Actions

1. **[P0] `/harden`** — Add ARIA labels, landmarks, focus indicators, skip-to-content link, form labels, and reduced-motion support across all components
2. **[P0] `/normalize`** — Convert all hard-coded colors to design tokens; add dark mode support via `prefers-color-scheme`
3. **[P1] `/adapt`** — Enlarge touch targets to 44px minimum; add mobile fallback for upload table grid
4. **[P1] `/optimize`** — Lazy-load all route modules; fix polling stale-closure in DatabaseModule
5. **[P2] `/extract`** — Move inline styles to CSS classes; consolidate repeated grid patterns
6. **[P2] `/typeset`** — Replace generic Helvetica Neue with a more distinctive typeface to match the clay aesthetic
7. **[P2] `/clarify`** — Add accessible labels to chat input and file upload inputs
8. **[P3] `/onboard`** — Improve empty states with guidance and calls to action
9. **[P3] `/polish`** — Replace `window.confirm()` with a styled dialog; add skeleton loading states
