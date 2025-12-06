# UI Consolidation Refactor - Execution Prompt

Use this prompt in a new Claude Code context to execute the refactor.

---

## PROMPT START

```
@console I need you to execute a comprehensive UI component consolidation refactor. This is a big-bang refactor that must run sub-agents in parallel, grouped by task type. You (main agent) must follow, validate, and fix any errors from sub-agents.

## Background

Analysis revealed significant variant bloat:
- TextVariant: 10 defined, 2 used → consolidate to 4
- TagVariant: 16 options, 6 unused → consolidate to 9
- ButtonVariant: `danger` unused, `lg` size unused → remove
- InputVariant: `search`/`code`/`secret` unused → remove
- primitives.ts: 107 exports, 12 unused, many duplicate RediaccX → clean up

Read the full plan: /packages/web/UI_CONSOLIDATION_REFACTOR.md

## Execution Order

### GROUP A (Run in Parallel) - Component Type Definitions

**Agent A1: Consolidate RediaccText variants**
- File: /packages/web/src/components/ui/Text/
- Keep only: body, caption, title, mono
- Remove: subtitle, helper, label, muted, danger, description
- Update TextVariant type, resolveTextVariantTokens, and component
- Search for any usage of removed variants and migrate them

**Agent A2: Consolidate RediaccTag variants**
- File: /packages/web/src/components/ui/Tag/
- Keep variants: default, success, warning, error, info, neutral
- Keep presets: team, machine, region
- Remove: primary, secondary variants; cluster, pool, bridge, vault, status presets
- Update types and PRESET_VARIANT_MAP
- Search for any usage and migrate

**Agent A3: Simplify RediaccButton**
- File: /packages/web/src/components/ui/Button/
- Remove `danger` variant (0 uses)
- Remove `lg` size (0 uses)
- Update types and styles

**Agent A4: Simplify RediaccInput**
- File: /packages/web/src/components/ui/Form/Input/
- Remove `search`, `code`, `secret` variants (0 uses)
- Remove `lg` size (0 uses)
- Update types and styles

### WAIT FOR GROUP A TO COMPLETE, THEN RUN GROUP B

### GROUP B1 (Single Agent) - Delete Unused Primitives

Delete from /packages/web/src/styles/primitives.ts:
- NoMarginTitle, FeatureCard, SpacedCard, ContentSection
- CenteredRow, InputSlot, CenteredFooter, SectionMargin, InfoList
- FilterRangePicker, FilterCheckbox, pulseAnimation

### GROUP B2 (Run in Parallel) - Migrate Text Components

Migrate primitives.ts text components to RediaccText. Split by directory:

**Agent B2a: pages/ceph/**
**Agent B2b: pages/settings/**, pages/organization/**
**Agent B2c: pages/dashboard/**, pages/queue/**
**Agent B2d: components/common/**
**Agent B2e: components/resources/**
**Agent B2f: components/layout/**

Migration mappings:
- CardTitle → <RediaccText variant="title">
- HelperText → <RediaccText variant="caption">
- CaptionText → <RediaccText variant="caption" size="xs">
- FormLabel → <RediaccText variant="body" size="sm" weight="medium">
- TitleText → <RediaccText variant="title">
- SecondaryText → <RediaccText color="secondary">
- MonoText → <RediaccText variant="mono">
- ItalicText → <RediaccText style={{ fontStyle: 'italic' }} color="secondary">

For styled extensions: styled(CardTitle) → styled(RediaccText).attrs({ variant: 'title' })

### GROUP B3 (Single Agent) - Migrate Tag Components

Migrate primitives.ts tag components to RediaccTag:
- StatusTag → RediaccTag with appropriate variant
- PillTag → RediaccTag with size prop
- StatusBadge → RediaccTag styled
- StatusTagSmall → RediaccTag size="sm"

### GROUP B4 (Single Agent) - Clean Primitives Types

After B2 and B3 complete, remove from primitives.ts:
- StatusVariant, TagVariant, TagSize types (now in RediaccTag.types.ts)
- STATUS_TOKEN_KEYS, TAG_TOKEN_KEYS constants
- resolveStatusTokens, resolveTagVariantTokens functions
- resolveTagPadding, resolveTagRadius, resolveTagFontSize functions

Update files importing these to use @/components/ui/Tag instead.

### WAIT FOR GROUP B TO COMPLETE

### GROUP C (Validation) - Run Sequentially

1. Run TypeScript: npx tsc --noEmit
2. Fix any type errors found
3. Run build: npm run build
4. Fix any build errors
5. Report final status

## Critical Rules

1. ALWAYS run tsc --noEmit after each group completes to catch errors early
2. When migrating, preserve visual styling (same colors, sizes, weights)
3. Handle styled extensions carefully - update base component properly
4. Grep before deleting - verify 0 usages
5. Import RediaccText/RediaccTag from @/components/ui barrel

## Expected Outcome

- TextVariant: 10 → 4 (60% reduction)
- TagVariant+Preset: 16 → 9 (44% reduction)
- ButtonVariant: 2 → 1 (50% reduction)
- InputVariant: 4 → 1 (75% reduction)
- primitives.ts exports: 107 → ~70 (35% reduction)

Execute this refactor now. Start with Group A in parallel.
```

## PROMPT END

---

## Tips for Execution

1. **Copy the entire prompt** between the ``` marks above
2. **Paste into a new Claude Code context** with the console package open
3. **The main agent will orchestrate** sub-agents and validate
4. **Expect ~20-30 minutes** for full execution
5. **If errors occur**, the main agent should fix them before proceeding

## Alternative: Phased Execution

If you prefer more control, execute in phases:

### Phase 1 Prompt
```
@console Execute only Group A from /packages/web/UI_CONSOLIDATION_REFACTOR.md - consolidate RediaccText, RediaccTag, RediaccButton, and RediaccInput variants. Run all 4 agents in parallel. After completion, run tsc --noEmit to validate.
```

### Phase 2 Prompt
```
@console Execute Group B from /packages/web/UI_CONSOLIDATION_REFACTOR.md - delete unused primitives, migrate text components to RediaccText (parallel by directory), migrate tag components to RediaccTag, clean primitives types. Run tsc --noEmit after each sub-phase.
```

### Phase 3 Prompt
```
@console Run final validation: tsc --noEmit, npm run build, check for any console errors or warnings. Report summary of changes.
```
