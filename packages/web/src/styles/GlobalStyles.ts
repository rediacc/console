import { createGlobalStyle, css } from 'styled-components'
import { colorTokens } from '@/config/antdTheme'

const toCssVars = (tokens: Record<string, string>) =>
  Object.entries(tokens)
    .filter(([, value]) => typeof value === 'string')
    .map(([key, value]) => `--color-${key.replace(/([A-Z])/g, '-$1').toLowerCase()}: ${value};`)
    .join('\n')

const MODAL_SIZES = {
  sm: { width: 480, height: 640, vh: 85, widthPct: 90 },
  md: { width: 720, height: 800, vh: 88, widthPct: 92 },
  lg: { width: 1200, height: 960, vh: 90, widthPct: 90 },
  xl: { width: 1400, height: 1120, vh: 92, widthPct: 95 },
  full: { width: 1600, height: 1280, vh: 95, widthPct: 98 },
} as const

const fontStack = css`
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif, 'Apple Color Emoji', 'Segoe UI Emoji', 'Segoe UI Symbol', 'Noto Color Emoji' !important;
`

const focusStyles = css`
  border-color: ${({ theme }) => theme.colors.primary} !important;
  box-shadow: 0 0 0 1px ${({ theme }) => theme.colors.primary} !important;
  outline: none !important;
`

const scrollbarStyles = css`
  scrollbar-color: #4a4a4a #1a1a1a;

  &::-webkit-scrollbar {
    background-color: #1a1a1a;
  }

  &::-webkit-scrollbar-thumb {
    background-color: #4a4a4a;
  }

  &::-webkit-scrollbar-thumb:hover {
    background-color: #5a5a5a;
  }
`

export const GlobalStyles = createGlobalStyle`
  /* ============================================
     GLOBAL RESETS
     ============================================ */
  
  * {
    box-sizing: border-box;
  }

  html,
  body {
    margin: 0;
    padding: 0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    line-height: 1.6;
  }

  #root {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }

  /* ============================================
     BODY THEME STYLES
     ============================================ */
  
  body[data-theme="light"] {
    background-color: #ffffff;
    color: #212529;
  }

  body[data-theme="dark"] {
    background-color: #0a0a0a;
    color: #fafafa;
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
     CSS COLOR VARIABLES (replacing themes.css)
     ============================================ */
  

  
  :root {
    ${toCssVars(colorTokens as unknown as Record<string, string>)}
  }
  
  [data-theme="light"] {
    ${toCssVars(colorTokens.light)}
  }
  
  [data-theme="dark"] {
    ${toCssVars(colorTokens.dark)}
  }

  /* ============================================
     SELECT COMPONENT GLOBAL STYLES
     ============================================ */
  
  /* Select text and icon colors - consistent across all selects */
  .ant-select-selection-item {
    color: ${({ theme }) => theme.colors.textPrimary} !important;
  }

  .ant-select-arrow {
    color: ${({ theme }) => theme.colors.textTertiary} !important;
  }

  /* When select is open/focused */
  .ant-select-open .ant-select-selection-item {
    color: ${({ theme }) => theme.colors.textPrimary} !important;
  }

  .ant-select-open .ant-select-arrow {
    color: ${({ theme }) => theme.colors.primary} !important;
  }

  /* Select focus state */
  .ant-select:focus-visible,
  .ant-select-focused {
    outline: none !important;
  }

  .ant-select-focused .ant-select-selector {
    border-color: ${({ theme }) => theme.colors.primary} !important;
    box-shadow: 0 0 0 1px ${({ theme }) => theme.colors.primary} !important;
    border-radius: 6px !important;
  }

  /* ============================================
     ANTD DROPDOWN EMOJI SUPPORT
     ============================================ */
  
  /* Dropdown container - emoji font support */
  /* Dropdown container - emoji font support */
  .ant-select-dropdown,
  .ant-select-item-option-content,
  .ant-select-selection-item {
    ${fontStack}
  }

  /* Fix suffix icon alignment and spacing */
  .ant-select-arrow {
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    margin-right: 8px !important;
    pointer-events: none !important;
    height: auto !important;
  }

  /* Fix selection item padding to prevent icon overlap */
  .ant-select-selection-item {
    padding-right: 24px !important;
  }

  /* Ensure proper spacing in selector */
  .ant-select-selector {
    display: flex !important;
    align-items: center !important;
  }

  /* ============================================
     INPUT AUTOFILL STYLES
     ============================================ */
  
  /* Override Chrome's autofill yellow background - global for all inputs */
  input:-webkit-autofill,
  input:-webkit-autofill:hover,
  input:-webkit-autofill:focus,
  input:-webkit-autofill:active {
    -webkit-box-shadow: 0 0 0 30px ${({ theme }) => theme.colors.bgPrimary} inset !important;
    -webkit-text-fill-color: ${({ theme }) => theme.colors.textPrimary} !important;
    transition: background-color 5000s ease-in-out 0s;
  }

  /* ============================================
     FOCUS STATES - CONSISTENT ACROSS ALL COMPONENTS
     ============================================ */
  
  /* Smaller, subtle focus shadows */
  /* Smaller, subtle focus shadows */
  .ant-select-focused .ant-select-selector,
  .ant-picker-focused,
  .ant-btn:focus,
  .ant-switch:focus,
  .ant-checkbox-wrapper:focus-within,
  .ant-radio-wrapper:focus-within,
  .ant-tabs-tab:focus,
  .ant-menu-item:focus,
  .ant-dropdown-trigger:focus,
  .ant-table-tbody > tr:focus,
  .ant-pagination-item:focus {
    ${focusStyles}
  }

  /* ============================================
     THEME TRANSITIONS (from themes.css)
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

  /* Disable transitions for performance-critical elements */
  input, 
  textarea, 
  button {
    transition: none;
  }

  /* ============================================
     SCROLLBAR STYLES (from themes.css)
     ============================================ */
  
  [data-theme="dark"] {
    ${scrollbarStyles}
  }

  /* ============================================
     ACCESSIBILITY - FOCUS STATES
     ============================================ */
  
  :focus-visible {
    outline: 3px solid var(--color-primary);
    outline-offset: 2px;
    border-radius: 6px;
  }

  /* Override Ant Design's default focus-visible */
  /* Option 1: Subtle focus (recommended for accessibility) */
  .ant-btn:not(:disabled):focus-visible {
    outline: none !important;
    outline-offset: 0 !important;
    box-shadow: 0 0 0 2px ${({ theme }) => theme.colors.shadow} !important;
    border-color: var(--color-primary) !important;
    transition: all 0.2s ease !important;
  }

  /* Option 2: Completely disable (uncomment if needed, but not recommended for accessibility)
  .ant-btn:not(:disabled):focus-visible {
    outline: none !important;
    outline-offset: 0 !important;
    box-shadow: none !important;
    transition: none !important;
  }
  */

  a:focus-visible,
  button:focus-visible,
  [role="button"]:focus-visible,
  [tabindex]:focus-visible {
    outline: 3px solid var(--color-primary) !important;
    outline-offset: 2px;
    box-shadow: 0 0 0 4px ${({ theme }) => theme.colors.shadow};
    border-radius: 4px;
  }

  .ant-select:focus-visible,
  .ant-select-focused {
    outline: none !important;
  }

  /* ============================================
     BUTTON FIXES
     ============================================ */

  /* Fix primary button text color */
  .ant-btn-primary {
    color: #ffffff !important;
    
    &:hover,
    &:focus {
      color: #ffffff !important;
    }
    
    &:disabled {
      color: rgba(255, 255, 255, 0.5) !important;
    }
  }

  /* Fix primary button with icon */
  .ant-btn-primary .anticon {
    color: #ffffff !important;
  }

  /* ============================================
     SEGMENTED FIXES
     ============================================ */

  /* Fix segmented button text truncation */
  .ant-segmented-item-label {
    overflow: visible !important;
    text-overflow: clip !important;
    white-space: nowrap !important;
  }

  /* Ensure segmented items have enough space */
  .ant-segmented-item {
    min-width: auto !important;
    flex: 1 1 auto !important;
  }

  /* Fix segmented group to not constrain width */
  .ant-segmented {
    width: auto !important;
    min-width: fit-content !important;
  }

  /* ============================================
     ENHANCED INTERACTIONS
     ============================================ */

  .ant-btn-primary:hover {
    transform: translateY(-1px);
    box-shadow: ${({ theme }) => theme.shadows.BUTTON_HOVER};
  }

  /* ============================================
     VAULT EDITOR FORM STYLES
     ============================================ */

  /* Fix label vertical alignment in vault editor and resource forms */
  .vault-editor-form .ant-form-item-row,
  .resource-form-with-vault .ant-form-item-row {
    align-items: flex-start;
  }

  .vault-editor-form .ant-form-item-label,
  .resource-form-with-vault .ant-form-item-label {
    display: flex;
    align-items: flex-start;
    padding-top: 5px !important;
    padding-bottom: 0 !important;
  }

  .vault-editor-form .ant-form-item-label > label,
  .resource-form-with-vault .ant-form-item-label > label {
    display: flex;
    align-items: center;
    line-height: 32px;
    min-height: 32px;
  }

  /* ============================================
     FORM VALIDATION ERRORS
     ============================================ */

  .ant-form-item-has-error .ant-select-selector {
    border-color: var(--color-error) !important;
    border-width: 2px !important;
    box-shadow: 0 0 0 3px rgba(255, 107, 107, 0.15) !important;
    background-color: rgba(255, 107, 107, 0.02);
  }

  .ant-form-item-has-error .ant-form-item-explain-error {
    color: var(--color-error);
    font-weight: 500;
    font-size: 13px;
    margin-top: 6px;
    padding: 6px 12px;
    background-color: rgba(255, 107, 107, 0.08);
    border-radius: 6px;
    border-left: 3px solid var(--color-error);
  }

  [data-theme="dark"] .ant-form-item-has-error .ant-select-selector {
    background-color: rgba(255, 107, 107, 0.05);
  }

  [data-theme="dark"] .ant-form-item-has-error .ant-form-item-explain-error {
    background-color: rgba(255, 107, 107, 0.1);
    color: #ff9999;
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
    0%, 100% {
      opacity: 1;
    }
    50% {
      opacity: 0.5;
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
    padding: ${({ theme }) => theme.spacing['4']}px;
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

  @keyframes shimmer {
    0% {
      background-position: -200% 0;
    }
    100% {
      background-position: 200% 0;
    }
  }

  /* ============================================
     TABLE ENHANCEMENTS
     ============================================ */

  .ant-table-tbody > tr.ant-table-row-selected > td {
    background: var(--color-bg-selected) !important;
  }

  .ant-table-tbody > tr.ant-table-row-selected:hover > td {
    background: var(--color-bg-active) !important;
  }

  [data-theme="dark"] .ant-table-tbody > tr.ant-table-row-selected > td {
    background: var(--color-bg-selected) !important;
  }

  [data-theme="dark"] .ant-table-tbody > tr.ant-table-row-selected:hover > td {
    background: var(--color-bg-active) !important;
  }

  /* ============================================
     MENU ENHANCEMENTS
     ============================================ */

  .ant-menu-item-selected .anticon {
    color: var(--color-primary) !important;
  }

  .ant-menu-item-divider {
    height: 1px !important;
    margin: 12px 16px !important;
    background-color: var(--color-border-primary) !important;
  }

  /* ============================================
     LAYOUT
     ============================================ */

  .ant-layout {
    min-height: 100vh;
  }

  /* No-scroll pages (Audit, Resources, Queue) */
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
     PAGINATION FIXES
     ============================================ */

  /* Fix pagination button text colors */
  .ant-pagination-item {
    background-color: ${({ theme }) => theme.colors.bgPrimary};
    border-color: ${({ theme }) => theme.colors.borderPrimary};
    
    a {
      color: ${({ theme }) => theme.colors.textPrimary} !important;
    }
    
    &:hover {
      border-color: ${({ theme }) => theme.colors.primary};
      
      a {
        color: ${({ theme }) => theme.colors.primary} !important;
      }
    }
  }

  .ant-pagination-item-active {
    background-color: var(--color-bg-selected);
    border-color: var(--color-bg-selected);

    a {
      color: var(--color-text-selected) !important;
    }

    &:hover {
      background-color: var(--color-bg-selected);
      border-color: var(--color-bg-selected);
      opacity: 0.9;

      a {
        color: var(--color-text-selected) !important;
      }
    }
  }

  /* Fix prev/next button colors */
  .ant-pagination-prev,
  .ant-pagination-next {
    .ant-pagination-item-link {
      color: ${({ theme }) => theme.colors.textPrimary} !important;
      background-color: ${({ theme }) => theme.colors.bgPrimary};
      border-color: ${({ theme }) => theme.colors.borderPrimary};
    }
    
    &:hover .ant-pagination-item-link {
      color: ${({ theme }) => theme.colors.primary} !important;
      border-color: ${({ theme }) => theme.colors.primary};
    }
    
    &.ant-pagination-disabled .ant-pagination-item-link {
      color: ${({ theme }) => theme.colors.textTertiary} !important;
      background-color: ${({ theme }) => theme.colors.bgSecondary};
      border-color: ${({ theme }) => theme.colors.borderSecondary};
      cursor: not-allowed;
    }
  }

  /* Fix pagination options (page size selector) */
  .ant-pagination-options {
    .ant-select-selector {
      color: ${({ theme }) => theme.colors.textPrimary} !important;
    }
  }

  /* ============================================
     MODAL RESPONSIVE SIZING SYSTEM
     ============================================ */

  /* Modal animations */
  .ant-modal-content {
    animation: fadeIn 0.3s ease-in-out;
  }

  /* Modal scrollbar styling */
  .ant-modal-body::-webkit-scrollbar {
    width: 8px;
  }

  .ant-modal-body::-webkit-scrollbar-track {
    background: transparent;
  }

  .ant-modal-body::-webkit-scrollbar-thumb {
    background-color: ${({ theme }) => theme.colors.borderSecondary};
    border-radius: 4px;
  }

  .ant-modal-body::-webkit-scrollbar-thumb:hover {
    background-color: ${({ theme }) => theme.colors.textSecondary};
  }

  /* Mobile responsive styles - applies to ALL modals */
  @media (max-width: 768px) {
    .ant-modal {
      max-width: calc(100vw - 32px) !important;
      margin: 16px auto;
    }

    .ant-modal-content {
      max-height: calc(100vh - 32px);
      overflow-y: auto;
    }

    .ant-modal-body {
      padding: ${({ theme }) => theme.spacing.MD}px;
    }

    .ant-tabs-nav {
      margin-bottom: ${({ theme }) => theme.spacing.SM}px;
    }

    .ant-list-item {
      flex-direction: column;
      align-items: flex-start;
      gap: ${({ theme }) => theme.spacing.SM}px;

      .ant-list-item-action {
        margin-left: 0;
        margin-top: ${({ theme }) => theme.spacing.XS}px;
      }
    }
  }

  /* Notification dropdown - List.Item.Meta title margin fix */
  .notification-dropdown {
    .ant-list-item-meta-title {
      margin-top: 0 !important;
    }
  }

  /* Modal footer - better button alignment */
  .ant-modal-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: ${({ theme }) => theme.spacing.SM}px;
    flex-wrap: wrap;

    /* Buttons on the left (Import/Export) */
    > div:first-child {
      margin-right: auto;
    }

    /* Buttons on the right (Cancel/Create) */
    > button,
    > .ant-btn {
      margin-left: 0;
    }
  }

  /* Generated Modal Sizes */
  ${Object.entries(MODAL_SIZES).map(([size, { width, height, vh, widthPct }]) => css`
    .modal-${size} {
      max-width: ${width}px !important;
      width: ${widthPct}% !important;
    }

    .modal-${size} .ant-modal-body {
      max-height: min(${vh}vh, ${height}px);
      overflow-y: auto;
    }
  `)}

  /* Fullscreen Modal - occupies entire browser viewport */
  .modal-fullscreen {
    max-width: 90vw !important;
    width: 90vw !important;
  }

  .modal-fullscreen .ant-modal-content {
    width: 90vw !important;
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
    max-height: unset !important;
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

  /* ============================================
     PRINT STYLES
     ============================================ */

  @media print {
    body {
      background: white !important;
    }
    
    .ant-layout-sider,
    .ant-layout-header,
    .no-print {
      display: none !important;
    }
    
    .ant-layout-content {
      padding: 0 !important;
    }
  }
`
