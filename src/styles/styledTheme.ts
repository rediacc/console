import { DESIGN_TOKENS } from '@/utils/styleConstants'
import { colorTokens } from '@/config/antdTheme'

export interface StyledTheme {
  // Colors
  colors: {
    primary: string
    primaryHover: string
    primaryBg: string
    secondary: string
    secondaryHover: string
    accent: string
    
    // Status colors
    success: string
    warning: string
    error: string
    info: string
    
    // Background colors
    bgPrimary: string
    bgSecondary: string
    bgTertiary: string
    bgHover: string
    bgActive: string
    bgSuccess: string
    bgWarning: string
    bgError: string
    bgInfo: string
    
    // Text colors
    textPrimary: string
    textSecondary: string
    textTertiary: string
    textMuted: string
    textInverse: string
    
    // Border colors
    borderPrimary: string
    borderSecondary: string
    borderHover: string
    
    // Shadow colors
    shadow: string
    shadowStrong: string
    
    // Input colors
    inputBg: string
    inputBorder: string
  }
  
  // Spacing
  spacing: typeof DESIGN_TOKENS.SPACING
  
  // Border radius
  borderRadius: typeof DESIGN_TOKENS.BORDER_RADIUS
  
  // Typography
  fontSize: typeof DESIGN_TOKENS.FONT_SIZE
  fontWeight: typeof DESIGN_TOKENS.FONT_WEIGHT
  lineHeight: typeof DESIGN_TOKENS.LINE_HEIGHT
  letterSpacing: typeof DESIGN_TOKENS.LETTER_SPACING
  
  // Dimensions
  dimensions: typeof DESIGN_TOKENS.DIMENSIONS
  
  // Shadows
  shadows: typeof DESIGN_TOKENS.SHADOWS
  
  // Z-index
  zIndex: typeof DESIGN_TOKENS.Z_INDEX
  
  // Transitions
  transitions: typeof DESIGN_TOKENS.TRANSITIONS
  
  // Breakpoints
  breakpoints: {
    mobile: string
    tablet: string
    desktop: string
    wide: string
  }
}

export const lightTheme: StyledTheme = {
  colors: {
    primary: colorTokens.primary,
    primaryHover: colorTokens.primaryHover,
    primaryBg: colorTokens.primaryBg,
    secondary: colorTokens.secondary,
    secondaryHover: colorTokens.secondaryHover,
    accent: colorTokens.accent,
    
    success: colorTokens.success,
    warning: colorTokens.warning,
    error: colorTokens.error,
    info: colorTokens.info,
    
    bgPrimary: colorTokens.light.bgPrimary,
    bgSecondary: colorTokens.light.bgSecondary,
    bgTertiary: colorTokens.light.bgTertiary,
    bgHover: colorTokens.light.bgHover,
    bgActive: colorTokens.light.bgActive,
    bgSuccess: '#d3f9d8',
    bgWarning: '#fff3cd',
    bgError: '#f8d7da',
    bgInfo: '#d1ecf1',
    
    textPrimary: colorTokens.light.textPrimary,
    textSecondary: colorTokens.light.textSecondary,
    textTertiary: colorTokens.light.textTertiary,
    textMuted: colorTokens.light.textMuted,
    textInverse: colorTokens.light.textInverse,
    
    borderPrimary: colorTokens.light.borderPrimary,
    borderSecondary: colorTokens.light.borderSecondary,
    borderHover: colorTokens.light.borderHover,
    
    shadow: colorTokens.light.shadow,
    shadowStrong: 'rgba(0, 0, 0, 0.15)',
    
    inputBg: colorTokens.light.bgPrimary,
    inputBorder: colorTokens.light.borderSecondary,
  },
  
  spacing: DESIGN_TOKENS.SPACING,
  borderRadius: DESIGN_TOKENS.BORDER_RADIUS,
  fontSize: DESIGN_TOKENS.FONT_SIZE,
  fontWeight: DESIGN_TOKENS.FONT_WEIGHT,
  lineHeight: DESIGN_TOKENS.LINE_HEIGHT,
  letterSpacing: DESIGN_TOKENS.LETTER_SPACING,
  dimensions: DESIGN_TOKENS.DIMENSIONS,
  shadows: DESIGN_TOKENS.SHADOWS,
  zIndex: DESIGN_TOKENS.Z_INDEX,
  transitions: DESIGN_TOKENS.TRANSITIONS,
  
  breakpoints: {
    mobile: '640px',
    tablet: '1024px',
    desktop: '1280px',
    wide: '1536px',
  },
}

export const darkTheme: StyledTheme = {
  colors: {
    primary: colorTokens.primary,
    primaryHover: colorTokens.primaryHover,
    primaryBg: colorTokens.primaryBg,
    secondary: colorTokens.secondary,
    secondaryHover: colorTokens.secondaryHover,
    accent: colorTokens.accent,
    
    success: colorTokens.success,
    warning: colorTokens.warning,
    error: colorTokens.error,
    info: colorTokens.info,
    
    bgPrimary: colorTokens.dark.bgPrimary,
    bgSecondary: colorTokens.dark.bgSecondary,
    bgTertiary: colorTokens.dark.bgTertiary,
    bgHover: colorTokens.dark.bgHover,
    bgActive: colorTokens.dark.bgActive,
    bgSuccess: '#155724',
    bgWarning: '#856404',
    bgError: '#721c24',
    bgInfo: '#004085',
    
    textPrimary: colorTokens.dark.textPrimary,
    textSecondary: colorTokens.dark.textSecondary,
    textTertiary: colorTokens.dark.textTertiary,
    textMuted: colorTokens.dark.textMuted,
    textInverse: colorTokens.dark.textInverse,
    
    borderPrimary: colorTokens.dark.borderPrimary,
    borderSecondary: colorTokens.dark.borderSecondary,
    borderHover: colorTokens.dark.borderHover,
    
    shadow: colorTokens.dark.shadow,
    shadowStrong: 'rgba(0, 0, 0, 0.5)',
    
    inputBg: colorTokens.dark.bgSecondary,
    inputBorder: colorTokens.dark.borderSecondary,
  },
  
  spacing: DESIGN_TOKENS.SPACING,
  borderRadius: DESIGN_TOKENS.BORDER_RADIUS,
  fontSize: DESIGN_TOKENS.FONT_SIZE,
  fontWeight: DESIGN_TOKENS.FONT_WEIGHT,
  lineHeight: DESIGN_TOKENS.LINE_HEIGHT,
  letterSpacing: DESIGN_TOKENS.LETTER_SPACING,
  dimensions: DESIGN_TOKENS.DIMENSIONS,
  shadows: DESIGN_TOKENS.SHADOWS,
  zIndex: DESIGN_TOKENS.Z_INDEX,
  transitions: DESIGN_TOKENS.TRANSITIONS,
  
  breakpoints: {
    mobile: '640px',
    tablet: '1024px',
    desktop: '1280px',
    wide: '1536px',
  },
}
