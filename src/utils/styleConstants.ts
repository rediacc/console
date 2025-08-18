export const DESIGN_TOKENS = {
  // Touch Targets - WCAG 2.1 AA compliance (minimum 44px)
  TOUCH_TARGET: {
    MIN_SIZE: 44,
    LARGE: 48,
    SMALL: 36, // Only for dense interfaces where 44px isn't practical
  },

  // Spacing Scale - 8px base system (matching style-guide.md)
  SPACING: {
    '0.5': 4,    // 0.5 * base
    '1': 8,      // 1 * base
    '1.5': 12,   // 1.5 * base
    '2': 16,     // 2 * base
    '2.5': 20,   // 2.5 * base
    '3': 24,     // 3 * base
    '4': 32,     // 4 * base
    '5': 40,     // 5 * base
    '6': 48,     // 6 * base
    '8': 64,     // 8 * base
    '10': 80,    // 10 * base
    '12': 96,    // 12 * base
    // Legacy aliases for backward compatibility
    MICRO: 2,
    XS: 4,
    SM: 8,
    MD: 16,
    LG: 24,
    XL: 32,
    XXL: 40,
    XXXL: 48,
    XXXXL: 56,
    XXXXXL: 64,
    XXXXXXL: 80,
    // Semantic spacing
    BASE: 8,
    CONTAINER: 24,
  },

  // Border Radius Scale (matching style-guide.md)
  BORDER_RADIUS: {
    NONE: 0,
    SM: 4,      // Small: 4px
    MD: 6,      // Medium: 6px
    LG: 8,      // Large: 8px
    XL: 12,     // X-Large: 12px
    XXL: 16,
    FULL: 9999, // Full: 9999px
    ROUND: '50%',
  },

  // Typography Scale (matching style-guide.md)
  FONT_SIZE: {
    CAPTION: 12,    // Caption: 12px / 0.75rem
    SM: 14,         // Body Small: 14px / 0.875rem
    BASE: 16,       // Body: 16px / 1rem
    LG: 18,         // Body Large: 18px / 1.125rem
    H5: 18,         // H5: 18px / 1.125rem
    H4: 20,         // H4: 20px / 1.25rem
    H3: 24,         // H3: 24px / 1.5rem
    H2: 30,         // H2: 30px / 1.875rem
    H1: 36,         // H1: 36px / 2.25rem
    DISPLAY: 48,    // Display: 48px / 3rem
    // Legacy aliases
    XS: 12,
    XL: 20,
    XXL: 24,
    XXXL: 32,
    XXXXL: 40,
    XXXXXL: 48,
    XXXXXXL: 64,
  },

  // Font Weights (matching style-guide.md)
  FONT_WEIGHT: {
    REGULAR: 400,   // Regular: 400
    MEDIUM: 500,    // Medium: 500
    SEMIBOLD: 600,  // Semibold: 600
    BOLD: 700,      // Bold: 700
    // Aliases
    NORMAL: 400,
  },

  // Line Heights (matching style-guide.md)
  LINE_HEIGHT: {
    TIGHT: 1.25,    // Tight: 1.25
    NORMAL: 1.5,    // Normal: 1.5
    RELAXED: 1.75,  // Relaxed: 1.75
    // Legacy aliases
    LOOSE: 1.8,
  },

  // Letter Spacing
  LETTER_SPACING: {
    TIGHT: '-0.5px',
    NORMAL: '0',
    WIDE: '0.5px',
    WIDER: '1px',
  },

  // Common Component Dimensions (matching style-guide.md)
  DIMENSIONS: {
    // Form inputs (style-guide specifies padding: 10px 14px)
    INPUT_HEIGHT: 44,      // Adjusted for WCAG touch target
    INPUT_HEIGHT_SM: 36,
    INPUT_HEIGHT_LG: 52,
    
    // Modals and cards (style-guide: max-width 560px for modals)
    MODAL_WIDTH: 560,      // Matching style-guide.md
    MODAL_WIDTH_SM: 400,
    MODAL_WIDTH_LG: 768,
    MODAL_WIDTH_XL: 1024,
    CARD_WIDTH: 320,
    CARD_WIDTH_LG: 400,
    
    // Navigation
    SIDEBAR_WIDTH: 280,
    HEADER_HEIGHT: 64,
    
    // Container widths (matching style-guide.md)
    CONTAINER_SM: 640,
    CONTAINER_MD: 768,
    CONTAINER_LG: 1024,
    CONTAINER_XL: 1280,
    CONTAINER_2XL: 1536,
    
    // Icons (matching style-guide.md: standard 20x20, small 16x16, large 24x24)
    ICON_SM: 16,
    ICON_MD: 20,     // Standard size
    ICON_LG: 24,
    ICON_XL: 32,
    ICON_XXL: 48,
    ICON_XXXL: 64,
  },

  // Shadows (matching style-guide.md)
  SHADOWS: {
    // Base shadows from style guide
    SM: '0 1px 2px rgba(0,0,0,0.05)',     // Small
    MD: '0 4px 6px rgba(0,0,0,0.1)',      // Medium  
    LG: '0 10px 15px rgba(0,0,0,0.1)',    // Large
    XL: '0 20px 25px rgba(0,0,0,0.1)',    // X-Large
    // Component-specific shadows
    CARD: '0 1px 3px rgba(0,0,0,0.1)',    // Cards: style-guide.md
    MODAL: '0 20px 25px rgba(0,0,0,0.1)', // Modals use XL shadow
    // CSS variable references
    BASE: 'var(--shadow-base)',
    // Specific shadows (keeping olive green theme)
    BUTTON_HOVER: '0 6px 20px rgba(85, 107, 47, 0.35)',
    BUTTON_DEFAULT: '0 4px 12px rgba(85, 107, 47, 0.25)',
    ERROR_FIELD: '0 4px 16px rgba(255, 107, 107, 0.25)',
    SIDEBAR: '2px 0 8px rgba(0,0,0,0.06)',
    SIDEBAR_DARK: '2px 0 8px rgba(0,0,0,0.3)',
    HEADER: '0 2px 8px rgba(0,0,0,0.06)',
    HEADER_DARK: '0 2px 8px rgba(0,0,0,0.3)',
  },

  // Z-Index Scale
  Z_INDEX: {
    DROPDOWN: 1000,
    MODAL: 1050,
    POPOVER: 1060,
    TOOLTIP: 1070,
    NOTIFICATION: 1080,
  },

  // Transitions (matching style-guide.md animation durations)
  TRANSITIONS: {
    FAST: '150ms cubic-bezier(0.4, 0, 0.2, 1)',      // Fast: 150ms
    NORMAL: '250ms cubic-bezier(0.4, 0, 0.2, 1)',    // Normal: 250ms
    SLOW: '400ms cubic-bezier(0.4, 0, 0.2, 1)',      // Slow: 400ms
    // Legacy aliases
    DEFAULT: '250ms cubic-bezier(0.4, 0, 0.2, 1)',
    // Specific animations with proper easing
    BUTTON: 'all 150ms cubic-bezier(0.4, 0, 0.2, 1)',
    HOVER: 'all 250ms cubic-bezier(0.4, 0, 0.2, 1)',
    MODAL: 'all 400ms cubic-bezier(0.4, 0, 0.2, 1)',
    // Easing functions from style guide
    EASE_IN_OUT: 'cubic-bezier(0.4, 0, 0.2, 1)',
    EASE_OUT: 'cubic-bezier(0, 0, 0.2, 1)',
    EASE_IN: 'cubic-bezier(0.4, 0, 1, 1)',
  },
} as const

// Style object generators for common patterns
export const createTouchTargetStyle = (size: number = DESIGN_TOKENS.TOUCH_TARGET.MIN_SIZE) => ({
  width: size,
  height: size,
  minWidth: size,
  minHeight: size,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
})

export const createCardStyle = (width?: number | string) => ({
  width: width || '100%',
  maxWidth: 'calc(100vw - 32px)',
  borderRadius: DESIGN_TOKENS.BORDER_RADIUS.LG,  // Cards: 8px border radius
  boxShadow: DESIGN_TOKENS.SHADOWS.CARD,
  border: '1px solid var(--color-border-secondary)',  // As per style guide
  background: 'var(--color-bg-primary)',
  padding: DESIGN_TOKENS.SPACING['3'],  // 24px padding as per style guide
})

export const createModalStyle = (width?: number) => ({
  width: width || DESIGN_TOKENS.DIMENSIONS.MODAL_WIDTH,
  maxWidth: 'calc(100vw - 32px)',
  borderRadius: DESIGN_TOKENS.BORDER_RADIUS.XL,  // Modals: 12px border radius
  boxShadow: DESIGN_TOKENS.SHADOWS.MODAL,
  border: 'none',
  background: 'var(--color-bg-primary)',
  padding: DESIGN_TOKENS.SPACING['4'],  // 32px padding as per style guide
})

export const createInputStyle = (height?: number) => ({
  // Most styles are handled by CSS classes (.ant-input, etc.)
  // Only return minimal overrides if absolutely necessary
  // CSS already handles: min-height, border-radius, font-size, padding, border, transition
})

export const createButtonStyle = (variant: 'primary' | 'secondary' | 'ghost' = 'primary') => {
  // Most button styles are handled by CSS classes (.ant-btn, .ant-btn-primary, etc.)
  // CSS already handles: min-height, border-radius, font-size, font-weight, padding, transition
  // Only return variant-specific overrides if absolutely necessary
  
  switch (variant) {
    case 'primary':
      return {
        // Primary button styles handled by .ant-btn-primary CSS class
      }
    case 'secondary':
      return {
        // Secondary button styles handled by .ant-btn-default CSS class
      }
    case 'ghost':
      return {
        // Ghost button styles handled by .ant-btn-ghost CSS class
      }
    default:
      return {}
  }
}

export const createTypographyStyle = (
  size: keyof typeof DESIGN_TOKENS.FONT_SIZE,
  weight?: keyof typeof DESIGN_TOKENS.FONT_WEIGHT,
  lineHeight?: keyof typeof DESIGN_TOKENS.LINE_HEIGHT
) => ({
  fontSize: DESIGN_TOKENS.FONT_SIZE[size],
  fontWeight: weight ? DESIGN_TOKENS.FONT_WEIGHT[weight] : undefined,
  lineHeight: lineHeight ? DESIGN_TOKENS.LINE_HEIGHT[lineHeight] : undefined,
})

// Spacing utilities
export const spacing = (size: keyof typeof DESIGN_TOKENS.SPACING) => DESIGN_TOKENS.SPACING[size]
export const borderRadius = (size: keyof typeof DESIGN_TOKENS.BORDER_RADIUS) => DESIGN_TOKENS.BORDER_RADIUS[size]
export const fontSize = (size: keyof typeof DESIGN_TOKENS.FONT_SIZE) => DESIGN_TOKENS.FONT_SIZE[size]
export const fontWeight = (weight: keyof typeof DESIGN_TOKENS.FONT_WEIGHT) => DESIGN_TOKENS.FONT_WEIGHT[weight]

// Media query helpers (matching style-guide.md responsive breakpoints)
export const BREAKPOINTS = {
  MOBILE: 640,     // Mobile: < 640px
  TABLET: 1024,    // Tablet: 640px - 1024px  
  DESKTOP: 1280,   // Desktop: 1024px - 1280px
  WIDE: 1536,      // Wide: > 1280px
  // Legacy aliases for backward compatibility
  XS: 480,
  SM: 640,
  MD: 768,
  LG: 1024,
  XL: 1280,
  XXL: 1536,
} as const

export const mediaQuery = (breakpoint: keyof typeof BREAKPOINTS) => 
  `@media (min-width: ${BREAKPOINTS[breakpoint]}px)`