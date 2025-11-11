# Styling Guide

This document captures the styling architecture introduced in PR #84 (_merged on October 19, 2025_) and PR #119 (_merged on October 29, 2025_) by @mehmethelveci. It exists so we can keep the styled-components migration consistent, make future CSS work easier to centralise, and give Claude (or any other AI pair) a canonical reference.

---

## Core Principles
- **Single source of truth:** Reuse the design tokens in `src/utils/styleConstants.ts`, the color map in `src/config/antdTheme.ts`, and the `StyledTheme` exported from `src/styles/styledTheme.ts`.
- **Co-located styles:** Every React module that owns UI markup keeps a sibling `styles.ts` file. Shared primitives belong in `src/styles/` or an existing component library folder.
- **Theme awareness:** All new styles must respect the current `DefaultTheme` provided by `ThemeContext`. Never hard-code colors or spacing when a token already exists.
- **Minimal globals:** `src/styles/GlobalStyles.ts` is the only place for cross-cutting resets and Ant Design overrides. Component-specific overrides should live with the component.
- **Progressive migration:** When touching a component that still relies on legacy CSS, migrate it fully to styled-components instead of layering on more `.css`.

---

## Folder & File Conventions
- `ComponentName/index.tsx` imports from `./styles` and never exports styled primitives itself.
- `styles.ts` files:
  - `import styled from 'styled-components'` as the default.
  - Wrap Ant Design parts via `styled(Button)` / `styled(Modal)` so tokens are available.
  - Use semantic names (`NotificationDropdown`, `LoginCard`) instead of generic wrappers.
  - Prefix transient props with `$` (e.g. `$isRead`) so styled-components strips them from the DOM. See `NotificationBell/styles.ts` and `QueueItemTraceModal/styles.ts`.
- Keep unused keyframes or helper functions out of the file; PR #119 removed legacy animations for this reason.

---

## Theme & Token Usage
- Access spacing via `theme.spacing` or `DESIGN_TOKENS.SPACING`. Prefer the descriptive keys (`theme.spacing.MD`) over raw numbers.
- Border radius, shadows, typography, and transitions should all come from `theme.borderRadius`, `theme.shadows`, `theme.fontSize`, and `theme.transitions`.
- Colors:
  - Prefer `theme.colors.*` on components that render inside the `ThemeProvider`.
  - Use CSS variables (`var(--color-*)`) when a value must be shared with pure CSS context (e.g. Ant Design dropdown content). `GlobalStyles` defines these per `data-theme`.

---

## Working With Ant Design
- Wrap Ant Design components in styled wrappers rather than targeting them from outside. Example: `export const StyledModal = styled(Modal)\`...\`` in `QueueItemTraceModal`.
- When overrides must stay global (selects, autofill, pagination), add them to `GlobalStyles.ts` inside a clearly labelled section. Follow the existing comment blocks:
  ```ts
  /* ============================================
     SECTION TITLE
     ============================================ */
  ```
- Keep `!important` usage minimal and document why inside the comment block if it is unavoidable.
- For dropdowns/selects, ensure emoji-friendly font stacks and arrow alignment match the existing overrides in `GlobalStyles.ts`.

---

## Modal Sizing System
Global classes live in `GlobalStyles.ts` and should be applied via the `className` prop on Ant Design modals:

| Class | Max Width | Typical Use |
|-------|-----------|-------------|
| `modal-sm` | 480px | Simple confirmations, short forms |
| `modal-md` | 720px | Standard forms |
| `modal-lg` | 1200px | Complex forms / tables |
| `modal-xl` | 1400px | Full-featured workflows |
| `modal-full` | 1600px | Dashboards, wide tables |
| `modal-fullscreen` | 100vw / 100vh | Full viewport experiences |

Each modal body automatically constrains height and scroll behaviour for the fixed desktop canvas. Do not duplicate these rules elsewhere—set the class and trust the global system.

---

## Animations & Transitions
- Use `styled-components` `keyframes` helpers in the module that needs them. PR #119 keeps only the animations that are actually applied.
- Reuse transition tokens (`theme.transitions.DEFAULT`, etc.) so hover/focus states remain consistent.
- For frequently reused animations, promote them to `src/styles/animations.ts` (create the file when we have at least two consumers).

---

## Adding or Migrating Components
1. **Create** or update the component’s `styles.ts`.
2. **Import** tokens from the theme—no ad-hoc constants.
3. **Keep** accessibility in mind. Icon buttons should use the control surface sizes in `DESIGN_TOKENS.DIMENSIONS`, and scroll areas should style their scrollbars like the existing modals.
4. **Annotate** tricky overrides with a short comment.
5. **Delete** the old `.css` file once the component compiles and renders correctly in both light and dark themes.

Before opening a PR, run through this quick checklist:
- [ ] Component renders correctly in light + dark themes.
- [ ] No raw hex/RGB values when a token exists.
- [ ] Modal sizing, if applicable, uses the shared classes.
- [ ] Ant Design overrides live either inside the styled wrapper or `GlobalStyles`.
- [ ] Dead CSS and unused imports have been removed.

---

## Common TypeScript & Linter Issues

### Styled Ant Design Table Components
When wrapping Ant Design's `Table` in styled-components with custom props:
```ts
// ✅ Correct: Cast to any to allow generic types and custom props
export const DataTable = styled(Table as any)<{ $isLoading?: boolean }>`
  .ant-spin-nested-loading {
    opacity: ${(props: any) => (props.$isLoading ? 0.65 : 1)};
  }
`
```

### Pagination Callbacks
Always provide explicit types for pagination callbacks to avoid implicit `any`:
```tsx
// ✅ Correct
showTotal: (total: number, range: [number, number]) => `${start} - ${end} of ${total}`,
onChange: (page: number, size: number) => { ... }
```

### React Hooks: setState in useEffect
When intentionally calling `setState` in `useEffect` (e.g., syncing with props):
```tsx
useEffect(() => {
  // eslint-disable-next-line react-hooks/set-state-in-effect
  setVaultData(parsed)
}, [initialVault])
```
Use this sparingly—only when synchronizing component state with external changes.

---

## Prompt Template for Claude (or other assistants)
```
You are updating styles in the console repo.
- Follow the conventions in STYLE.md.
- Use styled-components with the existing theme tokens.
- Co-locate styles in ComponentName/styles.ts and remove legacy CSS.
- Apply global modal sizing classes instead of duplicating layout rules.
- Prefer theme.spacing / theme.colors over literal values.
- Ensure new props passed to styled components are prefixed with $ to avoid leaking to the DOM.
- Verify changes in both light and dark themes.
```

Feel free to copy this prompt into CLAUDE.md or the PR description when requesting automated edits.
