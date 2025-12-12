import { createGlobalStyle, css } from 'styled-components';
import { colorTokens } from '@/config/antdTheme';

const toCssVars = (tokens: Record<string, string>) =>
  Object.entries(tokens)
    .filter(([, value]) => typeof value === 'string')
    .map(([key, value]) => `--color-${key.replace(/([A-Z])/g, '-$1').toLowerCase()}: ${value};`)
    .join('\n');

const MODAL_SIZES = {
  sm: { width: 480, height: 640, vh: 85, vw: 90 },
  md: { width: 720, height: 800, vh: 88, vw: 92 },
  lg: { width: 1200, height: 960, vh: 90, vw: 90 },
  xl: { width: 1400, height: 1120, vh: 92, vw: 95 },
  full: { width: 1600, height: 1280, vh: 95, vw: 98 },
} as const;

const scrollbarStyles = css`
  scrollbar-color: var(--color-secondary) var(--color-primary);

  &::-webkit-scrollbar {
    background-color: var(--color-primary);
  }

  &::-webkit-scrollbar-thumb {
    background-color: var(--color-secondary);
  }

  &::-webkit-scrollbar-thumb:hover {
    background-color: var(--color-accent);
  }
`;

export const GlobalStyles = createGlobalStyle`
  /* ============================================
     GLOBAL RESETS
     ============================================ */

  *,
  *::before,
  *::after {
    box-sizing: border-box;
  }

  html,
  body {
    margin: 0;
    padding: 0;
    font-family: ${({ theme }) => theme.fontFamily.SYSTEM};
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    line-height: 1.6;
    background-color: var(--color-bg-primary, #ffffff);
    color: var(--color-text-primary, #1a1a1a);
  }

  #root {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }

  body[data-theme='light'] {
    background-color: var(--color-bg-primary);
    color: var(--color-text-primary);
  }

  body[data-theme='dark'] {
    background-color: var(--color-bg-primary);
    color: var(--color-text-primary);
  }

  /* ============================================
     PAGE LAYOUT SYSTEM
     ============================================ */

  .main-layout-content {
    --page-padding: ${({ theme }) => theme.spacing.PAGE_CONTAINER}px;
    --page-section-gap: ${({ theme }) => theme.spacing.PAGE_SECTION_GAP}px;
    --page-card-padding: ${({ theme }) => theme.spacing.PAGE_CARD_PADDING}px;
  }

  .page-container {
    width: 100%;
    max-width: 100%;
    margin: 0 auto;
    padding: var(--page-padding, ${({ theme }) => theme.spacing.PAGE_CONTAINER}px);
  }

  .page-stack {
    display: flex;
    flex-direction: column;
    gap: var(--page-section-gap, ${({ theme }) => theme.spacing.PAGE_SECTION_GAP}px);
  }

  .page-card {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    background-color: ${({ theme }) => theme.colors.bgPrimary};
    box-shadow: ${({ theme }) => theme.shadows.CARD};
    border: 1px solid var(--color-border-secondary);
    overflow: hidden;
  }

  .page-card .ant-card-body {
    padding: var(--page-card-padding, ${({ theme }) => theme.spacing.PAGE_CARD_PADDING}px);
  }

  /* ============================================
     CSS COLOR VARIABLES
     ============================================ */

  :root {
    ${toCssVars(colorTokens as unknown as Record<string, string>)}
    --z-index-sticky: 10;
    --z-index-overlay: 100;
    /* Spacing CSS variables */
    --spacing-xxs: ${({ theme }) => theme.spacing.XXS}px;
    --spacing-xs: ${({ theme }) => theme.spacing.XS}px;
    --spacing-sm: ${({ theme }) => theme.spacing.SM}px;
    --spacing-sm-lg: ${({ theme }) => theme.spacing.SM_LG}px;
    --spacing-md: ${({ theme }) => theme.spacing.MD}px;
    --spacing-lg: ${({ theme }) => theme.spacing.LG}px;
    --spacing-xl: ${({ theme }) => theme.spacing.XL}px;
    --spacing-xxl: ${({ theme }) => theme.spacing.XXL}px;
    --spacing-xxxl: ${({ theme }) => theme.spacing.XXXL}px;
    /* Dimension CSS variables */
    --dimension-input-height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT}px;
    --dimension-control-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
    /* Overlay CSS variables */
    --overlay-nav-active: ${({ theme }) => theme.overlays.navActive};
    /* Transition CSS variables */
    --transition-default: ${({ theme }) => theme.transitions.DEFAULT};
    --transition-fast: ${({ theme }) => theme.transitions.FAST};
  }

  [data-theme='light'] {
    ${toCssVars(colorTokens.light)}
    --overlay-nav-active: ${({ theme }) => theme.overlays.navActive};
    --color-bg-container: ${({ theme }) => theme.colors.bgContainer};
    --color-fill-tertiary: ${({ theme }) => theme.colors.bgFillTertiary};
    --color-fill-quaternary: ${({ theme }) => theme.colors.bgFillQuaternary};
  }

  [data-theme='dark'] {
    ${toCssVars(colorTokens.dark)}
    --overlay-nav-active: ${({ theme }) => theme.overlays.navActive};
    --color-bg-container: ${({ theme }) => theme.colors.bgContainer};
    --color-fill-tertiary: ${({ theme }) => theme.colors.bgFillTertiary};
    --color-fill-quaternary: ${({ theme }) => theme.colors.bgFillQuaternary};
  }

  /* ============================================
     INPUT AUTOFILL
     ============================================ */

  input:-webkit-autofill,
  input:-webkit-autofill:hover,
  input:-webkit-autofill:focus,
  input:-webkit-autofill:active {
    -webkit-box-shadow: 0 0 0 30px ${({ theme }) => theme.colors.bgPrimary} inset;
    -webkit-text-fill-color: ${({ theme }) => theme.colors.textPrimary};
    transition: background-color 5000s ease-in-out 0s;
  }

  /* ============================================
     THEME TRANSITIONS
     ============================================ */

  body,
  .ant-layout,
  .ant-layout-header,
  .ant-layout-content,
  .ant-layout-sider,
  .ant-card,
  .ant-table,
  .ant-menu,
  .ant-modal-content {
    transition: background-color 0.15s ease, color 0.15s ease;
  }

  .ant-card,
  .ant-table-thead > tr > th,
  .ant-table-tbody > tr > td,
  .ant-select-selector {
    transition: border-color 0.15s ease;
  }

  input,
  textarea,
  button {
    transition: none;
  }

  /* ============================================
     SCROLLBARS
     ============================================ */

  [data-theme='dark'] {
    ${scrollbarStyles}
  }

  /* ============================================
     FOCUS STATES
     ============================================ */

  :focus-visible {
    outline: 3px solid var(--color-primary);
    outline-offset: 2px;
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
  }

  a:focus-visible,
  button:focus-visible,
  [role='button']:focus-visible,
  [tabindex]:focus-visible {
    outline: 3px solid var(--color-primary);
    outline-offset: 2px;
    box-shadow: 0 0 0 ${({ theme }) => theme.spacing.XS}px ${({ theme }) => theme.colors.shadow};
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  }

  /* ============================================
     ANIMATIONS
     ============================================ */

  @keyframes fadeIn {
    from {
      opacity: 0;
      transform: translateY(10px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  @keyframes slideIn {
    from {
      transform: translateX(-100%);
    }
    to {
      transform: translateX(0);
    }
  }

  @keyframes pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.5;
    }
  }

  @keyframes shimmer {
    0% {
      background-position: -200% 0;
    }
    100% {
      background-position: 200% 0;
    }
  }

  /* ============================================
     LOADING STATES
     ============================================ */

  .loading-container {
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 200px;
    padding: ${({ theme }) => theme.spacing.XL}px;
  }

  .skeleton-shimmer {
    background: linear-gradient(
      90deg,
      ${({ theme }) => theme.colors.bgSecondary} 25%,
      ${({ theme }) => theme.colors.bgTertiary} 50%,
      ${({ theme }) => theme.colors.bgSecondary} 75%
    );
    background-size: 200% 100%;
    animation: shimmer 1.5s ease-in-out infinite;
  }

  /* ============================================
     MODAL SIZES
     ============================================ */

  ${Object.entries(MODAL_SIZES).map(
    ([size, { width, height, vh, vw }]) => css`
      .modal-${size} {
        min-width: min(${width}px, ${vw}vw);
        max-width: min(${width}px, ${vw}vw);
      }

      .modal-${size} .ant-modal-body {
        max-height: min(${vh}vh, ${height}px);
        overflow-y: auto;
      }
    `
  )}

  .modal-fullscreen {
    min-width: 90vw;
    max-width: 90vw;
  }

  .modal-fullscreen .ant-modal-content {
    width: 90vw;
    display: flex;
    flex-direction: column;
  }

  .modal-fullscreen .ant-modal-header {
    flex-shrink: 0;
    border-bottom: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  }

  .modal-fullscreen .ant-modal-body {
    flex: 1;
    min-height: 0;
    max-height: unset;
    overflow-y: auto;
    padding: ${({ theme }) => theme.spacing.LG}px;
  }

  .modal-fullscreen .ant-modal-footer {
    flex-shrink: 0;
    border-top: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  }

  /* ============================================
     UTILITY CLASSES
     ============================================ */

  .number-format {
    font-feature-settings: 'tnum' 1;
    font-variant-numeric: tabular-nums;
  }

  .ant-statistic-content,
  .ant-progress-text,
  .metric-number {
    font-feature-settings: 'tnum' 1;
    font-variant-numeric: tabular-nums;
  }

  .notification-dropdown .ant-list-item-meta-title {
    margin-top: 0;
  }

  /* ============================================
     LAYOUT HELPERS
     ============================================ */

  .ant-layout {
    min-height: 100vh;
  }

  .no-scroll-page {
    height: 100vh;
    overflow: hidden;
  }

  .no-scroll-page .ant-layout-content {
    height: calc(100vh - 64px);
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  /* ============================================
     PRINT STYLES
     ============================================ */

  @media print {
    body {
      background: white;
    }

    .ant-layout-sider,
    .ant-layout-header,
    .no-print {
      display: none;
    }

    .ant-layout-content {
      padding: 0;
    }
  }
`;
