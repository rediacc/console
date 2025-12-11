export const DESIGN_TOKENS = {
  SPACING: {
    // Core scale (4px base)
    XXS: 2, // Extra extra small (micro adjustments)
    XS: 4, // Extra small
    SM: 8, // Small
    SM_LG: 12, // Small-Large (between SM and MD)
    MD: 16, // Medium
    LG: 24, // Large
    XL: 32, // Extra large
    XXL: 40, // 2x Extra large
    XXXL: 48, // 3x Extra large
    // Semantic aliases
    PAGE_CONTAINER: 16,
    PAGE_SECTION_GAP: 16,
    PAGE_CARD_PADDING: 16,
  },

  BORDER_RADIUS: {
    SM: 4,
    MD: 6,
    LG: 8,
    XL: 12,
    FULL: 9999,
  },

  FONT_SIZE: {
    XS: 12,
    CAPTION: 12,
    SM: 14,
    BASE: 16,
    LG: 18,
    H5: 18,
    H4: 20,
    XL: 20,
    XXXXXXL: 64,
  },

  FONT_WEIGHT: {
    REGULAR: 400,
    MEDIUM: 500,
    SEMIBOLD: 600,
    NORMAL: 400,
  },

  LINE_HEIGHT: {
    TIGHT: 1.25,
    NORMAL: 1.5,
    RELAXED: 1.75,
  },

  LETTER_SPACING: {
    TIGHT: '-0.5px',
    NORMAL: '0',
    WIDE: '0.5px',
  },

  DIMENSIONS: {
    // Control sizes
    CONTROL_HEIGHT: 32,
    CONTROL_HEIGHT_SM: 28,
    CONTROL_HEIGHT_LG: 40,
    INPUT_HEIGHT: 44,
    INPUT_HEIGHT_SM: 36,
    INPUT_HEIGHT_LG: 52,

    // Modal/Card widths
    MODAL_WIDTH: 560,
    MODAL_WIDTH_LG: 768,
    MODAL_WIDTH_XL: 1024,
    CARD_WIDTH: 320,
    CARD_WIDTH_LG: 400,

    // Layout
    SIDEBAR_WIDTH: 280,
    HEADER_HEIGHT: 64,
    MAX_CONTENT_WIDTH: 1200,
    SPLIT_PANEL_MIN_WIDTH: 300,

    // Container heights
    LIST_MAX_HEIGHT: 400,
    CONTENT_MIN_HEIGHT: 400,
    DROPDOWN_MAX_HEIGHT: 500,
    COMPACT_MAX_HEIGHT: 100,
    DASHBOARD_SECTION_HEIGHT: 200,
    VISUALIZATION_HEIGHT: 600,

    // Dropdown/Popover widths
    DROPDOWN_WIDTH_SM: 140,
    DROPDOWN_WIDTH_MD: 320,
    DROPDOWN_WIDTH_LG: 380,
    POPOVER_WIDTH: 400,
    TOOLTIP_MIN_WIDTH: 160,

    // Input/Filter widths
    SEARCH_INPUT_WIDTH: 300,
    FILTER_INPUT_WIDTH: 200,
    SELECTOR_MAX_WIDTH: 420,
    ERROR_WRAPPER_WIDTH: 480,
    LOGO_MAX_WIDTH: 150,

    // Icons
    ICON_SM: 16,
    ICON_MD: 20,
    ICON_LG: 24,
    ICON_XL: 32,
    ICON_XXL: 48,
    ICON_XXXL: 64,
  },

  SHADOWS: {
    SM: '0 1px 2px rgba(0,0,0,0.05)',
    MD: '0 4px 6px rgba(0,0,0,0.1)',
    XL: '0 20px 25px rgba(0,0,0,0.1)',
    CARD: '0 1px 3px rgba(0,0,0,0.1)',
    MODAL: '0 20px 25px rgba(0,0,0,0.1)',
    BUTTON_HOVER: '0 6px 20px rgba(85, 107, 47, 0.35)',
    BUTTON_DEFAULT: '0 4px 12px rgba(85, 107, 47, 0.25)',
    ERROR_FIELD: '0 4px 16px rgba(220, 53, 69, 0.25)',
    HEADER: '0 2px 8px rgba(0,0,0,0.06)',
    HEADER_DARK: '0 2px 8px rgba(0,0,0,0.3)',
    // Panel shadows (left-facing, for slide-in panels)
    PANEL_LEFT: '-2px 0 8px rgba(0, 0, 0, 0.15)',
    PANEL_LEFT_DARK: '-2px 0 8px rgba(0, 0, 0, 0.4)',
    // Switch/control handle shadow
    CONTROL_HANDLE: '0 2px 4px rgba(0, 0, 0, 0.2)',
    CONTROL_HANDLE_DARK: '0 2px 4px rgba(0, 0, 0, 0.4)',
    // Label text shadows (for contrast on busy backgrounds)
    LABEL_TEXT_LIGHT: '1px 1px 2px rgba(255, 255, 255, 0.8)',
    LABEL_TEXT_DARK: '1px 1px 2px rgba(0, 0, 0, 0.8)',
    // Ant Design compatible shadows (different blur/spread for component library)
    ANT_SM_LIGHT: '0 1px 3px rgba(0, 0, 0, 0.1)',
    ANT_SM_DARK: '0 1px 3px rgba(0, 0, 0, 0.3)',
    ANT_MD_LIGHT: '0 4px 12px rgba(0, 0, 0, 0.15)',
    ANT_MD_DARK: '0 4px 12px rgba(0, 0, 0, 0.4)',
    ANT_LG_LIGHT: '0 6px 16px rgba(0, 0, 0, 0.12)',
    ANT_LG_DARK: '0 6px 16px rgba(0, 0, 0, 0.4)',
    // Strong shadow for elevated elements (used by theme.colors.shadowStrong)
    SHADOW_STRONG_LIGHT: 'rgba(0, 0, 0, 0.15)',
    SHADOW_STRONG_DARK: 'rgba(0, 0, 0, 0.5)',
  },

  OVERLAYS: {
    // Modal/drawer backdrops
    BACKDROP_LIGHT: 'rgba(0, 0, 0, 0.4)',
    BACKDROP_DARK: 'rgba(0, 0, 0, 0.6)',
    // Loading/content overlays
    CONTENT_LIGHT: 'rgba(255, 255, 255, 0.85)',
    CONTENT_DARK: 'rgba(0, 0, 0, 0.75)',
    // Navigation active state
    NAV_ACTIVE_LIGHT: 'rgba(85, 107, 47, 0.1)',
    NAV_ACTIVE_DARK: 'rgba(106, 106, 106, 0.15)',
  },

  Z_INDEX: {
    STICKY: 10,
    OVERLAY: 100,
    DROPDOWN: 1000,
    MODAL: 1050,
    NOTIFICATION: 1080,
  },

  BREAKPOINTS: {
    MOBILE: 480,
    TABLET: 768,
    DESKTOP: 1024,
    WIDE: 1280,
  },

  TRANSITIONS: {
    FAST: '150ms cubic-bezier(0.4, 0, 0.2, 1)',
    SLOW: '400ms cubic-bezier(0.4, 0, 0.2, 1)',
    DEFAULT: '250ms cubic-bezier(0.4, 0, 0.2, 1)',
    BUTTON: 'all 150ms cubic-bezier(0.4, 0, 0.2, 1)',
    HOVER: 'all 250ms cubic-bezier(0.4, 0, 0.2, 1)',
  },
} as const;

// Style object generators for common patterns
export const createControlSurfaceStyle = (
  size: number = DESIGN_TOKENS.DIMENSIONS.CONTROL_HEIGHT
) => ({
  width: size,
  height: size,
  minWidth: size,
  minHeight: size,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
});

export const createCardStyle = (width?: number | string) => ({
  width: width || '100%',
  maxWidth: 'calc(100vw - 32px)',
  borderRadius: DESIGN_TOKENS.BORDER_RADIUS.LG, // Cards: 8px border radius
  boxShadow: DESIGN_TOKENS.SHADOWS.CARD,
  border: '1px solid var(--color-border-secondary)', // As per style guide
  background: 'var(--color-bg-primary)',
});

export const createModalStyle = (width?: number) => ({
  width: width || DESIGN_TOKENS.DIMENSIONS.MODAL_WIDTH,
  maxWidth: 'calc(100vw - 32px)',
  borderRadius: DESIGN_TOKENS.BORDER_RADIUS.XL, // Modals: 12px border radius
  boxShadow: DESIGN_TOKENS.SHADOWS.MODAL,
  border: 'none',
  padding: DESIGN_TOKENS.SPACING.XL, // 32px padding as per style guide
});

export const createInputStyle = (_height?: number) => ({
  // Most styles are handled by CSS classes (.ant-input, etc.)
  // Only return minimal overrides if absolutely necessary
  // CSS already handles: min-height, border-radius, font-size, padding, border, transition
});

export const createButtonStyle = (variant: 'primary' | 'secondary' | 'ghost' = 'primary') => {
  // Most button styles are handled by CSS classes (.ant-btn, .ant-btn-primary, etc.)
  // CSS already handles: min-height, border-radius, font-size, font-weight, padding, transition
  // Only return variant-specific overrides if absolutely necessary

  switch (variant) {
    case 'primary':
      return {
        // Primary button styles handled by .ant-btn-primary CSS class
      };
    case 'secondary':
      return {
        // Secondary button styles handled by .ant-btn-default CSS class
      };
    case 'ghost':
      return {
        // Ghost button styles handled by .ant-btn-ghost CSS class
      };
    default:
      return {};
  }
};

export const createTypographyStyle = (
  size: keyof typeof DESIGN_TOKENS.FONT_SIZE,
  weight?: keyof typeof DESIGN_TOKENS.FONT_WEIGHT,
  lineHeight?: keyof typeof DESIGN_TOKENS.LINE_HEIGHT
) => ({
  fontSize: DESIGN_TOKENS.FONT_SIZE[size],
  fontWeight: weight ? DESIGN_TOKENS.FONT_WEIGHT[weight] : undefined,
  lineHeight: lineHeight ? DESIGN_TOKENS.LINE_HEIGHT[lineHeight] : undefined,
});

// Spacing utilities
export const spacing = (size: keyof typeof DESIGN_TOKENS.SPACING) => DESIGN_TOKENS.SPACING[size];
export const borderRadius = (size: keyof typeof DESIGN_TOKENS.BORDER_RADIUS) =>
  DESIGN_TOKENS.BORDER_RADIUS[size];
export const fontSize = (size: keyof typeof DESIGN_TOKENS.FONT_SIZE) =>
  DESIGN_TOKENS.FONT_SIZE[size];
export const fontWeight = (weight: keyof typeof DESIGN_TOKENS.FONT_WEIGHT) =>
  DESIGN_TOKENS.FONT_WEIGHT[weight];
