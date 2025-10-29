import { createGlobalStyle } from 'styled-components'
import { colorTokens } from '@/config/antdTheme'

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
     CSS COLOR VARIABLES (replacing themes.css)
     ============================================ */
  
  :root {
    --color-primary: ${colorTokens.primary};
    --color-primary-hover: ${colorTokens.primaryHover};
    --color-primary-bg: ${colorTokens.primaryBg};
    --color-secondary: ${colorTokens.secondary};
    --color-secondary-hover: ${colorTokens.secondaryHover};
    --color-accent: ${colorTokens.accent};
    --color-success: ${colorTokens.success};
    --color-warning: ${colorTokens.warning};
    --color-error: ${colorTokens.error};
    --color-info: ${colorTokens.info};
  }
  
  [data-theme="light"] {
    --color-bg-primary: ${colorTokens.light.bgPrimary};
    --color-bg-secondary: ${colorTokens.light.bgSecondary};
    --color-bg-tertiary: ${colorTokens.light.bgTertiary};
    --color-bg-hover: ${colorTokens.light.bgHover};
    --color-bg-active: ${colorTokens.light.bgActive};
    --color-text-primary: ${colorTokens.light.textPrimary};
    --color-text-secondary: ${colorTokens.light.textSecondary};
    --color-text-tertiary: ${colorTokens.light.textTertiary};
    --color-text-muted: ${colorTokens.light.textMuted};
    --color-text-inverse: ${colorTokens.light.textInverse};
    --color-border-primary: ${colorTokens.light.borderPrimary};
    --color-border-secondary: ${colorTokens.light.borderSecondary};
    --color-border-hover: ${colorTokens.light.borderHover};
    --color-shadow: ${colorTokens.light.shadow};
  }
  
  [data-theme="dark"] {
    --color-bg-primary: ${colorTokens.dark.bgPrimary};
    --color-bg-secondary: ${colorTokens.dark.bgSecondary};
    --color-bg-tertiary: ${colorTokens.dark.bgTertiary};
    --color-bg-hover: ${colorTokens.dark.bgHover};
    --color-bg-active: ${colorTokens.dark.bgActive};
    --color-text-primary: ${colorTokens.dark.textPrimary};
    --color-text-secondary: ${colorTokens.dark.textSecondary};
    --color-text-tertiary: ${colorTokens.dark.textTertiary};
    --color-text-muted: ${colorTokens.dark.textMuted};
    --color-text-inverse: ${colorTokens.dark.textInverse};
    --color-border-primary: ${colorTokens.dark.borderPrimary};
    --color-border-secondary: ${colorTokens.dark.borderSecondary};
    --color-border-hover: ${colorTokens.dark.borderHover};
    --color-shadow: ${colorTokens.dark.shadow};
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
  .ant-select-dropdown {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif, 'Apple Color Emoji', 'Segoe UI Emoji', 'Segoe UI Symbol', 'Noto Color Emoji' !important;
  }

  /* Dropdown option content */
  .ant-select-item-option-content {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif, 'Apple Color Emoji', 'Segoe UI Emoji', 'Segoe UI Symbol', 'Noto Color Emoji' !important;
  }

  /* Selected item in dropdown */
  .ant-select-selection-item {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 'Cantarell', 'Fira Sans', 'Droid Sans', 'Helvetica Neue', sans-serif, 'Apple Color Emoji', 'Segoe UI Emoji', 'Segoe UI Symbol', 'Noto Color Emoji' !important;
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
  .ant-select-focused .ant-select-selector,
  .ant-picker-focused {
    border-color: ${({ theme }) => theme.colors.primary} !important;
    box-shadow: 0 0 0 1px ${({ theme }) => theme.colors.primary} !important;
    outline: none !important;
  }

  .ant-btn:focus,
  .ant-switch:focus,
  .ant-checkbox-wrapper:focus-within,
  .ant-radio-wrapper:focus-within,
  .ant-tabs-tab:focus,
  .ant-menu-item:focus,
  .ant-dropdown-trigger:focus,
  .ant-table-tbody > tr:focus,
  .ant-pagination-item:focus {
    border-color: ${({ theme }) => theme.colors.primary} !important;
    box-shadow: 0 0 0 1px ${({ theme }) => theme.colors.primary} !important;
    outline: none !important;
  }

  /* ============================================
     MOBILE RESPONSIVE - AUTH LAYOUT
     ============================================ */
  
  @media (max-width: 768px) {
    .auth-layout-content {
      padding: 0 !important;
    }
    
    /* Move theme toggle to bottom on mobile */
    .auth-theme-toggle-wrapper {
      position: fixed !important;
      top: auto !important;
      bottom: 24px !important;
      right: 24px !important;
      z-index: 1000 !important;
    }
  }

  /* ============================================
     MOBILE TOUCH TARGETS
     ============================================ */
  
  @media (max-width: 480px) {
    /* Enhanced touch targets for mobile */
    .ant-btn:focus,
    .ant-select-focused .ant-select-selector,
    .ant-radio-button-wrapper:focus {
      box-shadow: 0 0 0 1px ${({ theme }) => theme.colors.primary} !important;
      border-color: ${({ theme }) => theme.colors.primary} !important;
      outline: none !important;
    }
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
    scrollbar-color: #4a4a4a #1a1a1a;
  }

  [data-theme="dark"]::-webkit-scrollbar {
    background-color: #1a1a1a;
  }

  [data-theme="dark"]::-webkit-scrollbar-thumb {
    background-color: #4a4a4a;
  }

  [data-theme="dark"]::-webkit-scrollbar-thumb:hover {
    background-color: #5a5a5a;
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
    box-shadow: 0 0 0 2px rgba(85, 107, 47, 0.2) !important;
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
    box-shadow: 0 0 0 4px rgba(85, 107, 47, 0.25);
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
    box-shadow: 0 6px 20px rgba(85, 107, 47, 0.35);
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
    background: rgba(85, 107, 47, 0.08) !important;
  }

  .ant-table-tbody > tr.ant-table-row-selected:hover > td {
    background: rgba(85, 107, 47, 0.12) !important;
  }

  [data-theme="dark"] .ant-table-tbody > tr.ant-table-row-selected > td {
    background: rgba(125, 155, 73, 0.15) !important;
  }

  [data-theme="dark"] .ant-table-tbody > tr.ant-table-row-selected:hover > td {
    background: rgba(125, 155, 73, 0.2) !important;
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
    background-color: ${({ theme }) => theme.colors.primary};
    border-color: ${({ theme }) => theme.colors.primary};
    
    a {
      color: #ffffff !important;
    }
    
    &:hover {
      background-color: ${({ theme }) => theme.colors.primaryHover};
      border-color: ${({ theme }) => theme.colors.primaryHover};
      
      a {
        color: #ffffff !important;
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

  /* Small Modal - 480px max-width */
  .modal-sm {
    max-width: 480px !important;
    width: 90% !important;
  }

  .modal-sm .ant-modal-body {
    max-height: min(85vh, 640px);
    overflow-y: auto;
  }

  /* Medium Modal - 720px max-width */
  .modal-md {
    max-width: 720px !important;
    width: 92% !important;
  }

  .modal-md .ant-modal-body {
    max-height: min(88vh, 800px);
    overflow-y: auto;
  }

  /* Large Modal - 1200px max-width */
  .modal-lg {
    max-width: 1200px !important;
    width: 90% !important;
  }

  .modal-lg .ant-modal-body {
    max-height: min(90vh, 960px);
    overflow-y: auto;
  }

  /* Extra Large Modal - 1400px max-width */
  .modal-xl {
    max-width: 1400px !important;
    width: 95% !important;
  }

  .modal-xl .ant-modal-body {
    max-height: min(92vh, 1120px);
    overflow-y: auto;
  }

  /* Full Width Modal - 1600px max-width */
  .modal-full {
    max-width: 1600px !important;
    width: 98% !important;
  }

  .modal-full .ant-modal-body {
    max-height: min(95vh, 1280px);
    overflow-y: auto;
  }

  /* Fullscreen Modal - occupies entire browser viewport */
  .modal-fullscreen {
    max-width: 100vw !important;
    width: 100vw !important;
    height: 100vh !important;
    margin: 0 !important;
    top: 0 !important;
    padding: 0 !important;
  }

  .modal-fullscreen .ant-modal-content {
    height: 100vh !important;
    width: 100vw !important;
    border-radius: 0 !important;
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
    padding: 24px;
  }

  .modal-fullscreen .ant-modal-footer {
    flex-shrink: 0;
    border-top: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  }

  /* Responsive adjustments for tablets */
  @media (max-width: 768px) {
    .modal-sm { width: 95vw !important; }
    .modal-sm .ant-modal-body { max-height: 80vh; }
    
    .modal-md { width: 96vw !important; }
    .modal-md .ant-modal-body { max-height: 85vh; }
    
    .modal-lg { width: 97vw !important; }
    .modal-lg .ant-modal-body { max-height: 90vh; }
    
    .modal-xl { width: 98vw !important; }
    .modal-xl .ant-modal-body { max-height: 92vh; }
    
    .modal-full { width: 99vw !important; }
    .modal-full .ant-modal-body { max-height: 95vh; }
  }

  /* Responsive adjustments for mobile */
  @media (max-width: 480px) {
    .modal-sm { width: 98vw !important; }
    .modal-sm .ant-modal-body { max-height: 85vh; }
    
    .modal-md { width: 99vw !important; }
    .modal-md .ant-modal-body { max-height: 90vh; }
    
    .modal-lg { width: 99vw !important; }
    .modal-lg .ant-modal-body { max-height: 92vh; }
    
    .modal-xl { width: 99vw !important; }
    .modal-xl .ant-modal-body { max-height: 95vh; }
    
    .modal-full { width: 100vw !important; }
    .modal-full .ant-modal-body { max-height: 98vh; }
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
