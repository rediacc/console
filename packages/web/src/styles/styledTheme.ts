import { createColorTheme } from '@/styles/colorSystem';
import { DESIGN_TOKENS } from '@/utils/styleConstants';

export interface StyledTheme {
  // Colors
  colors: {
    primary: string;
    primaryHover: string;
    primaryBg: string;

    // Status colors
    success: string;
    warning: string;
    error: string;
    info: string;

    // Background colors
    bgPrimary: string;
    bgSecondary: string;
    bgTertiary: string;
    bgContainer: string; // Theme-aware container bg (light=bgPrimary, dark=bgSecondary)
    bgHover: string;
    bgActive: string;
    bgSelected: string; // High-contrast selection background
    bgSuccess: string;
    bgWarning: string;
    bgError: string;
    bgInfo: string;

    // Fill colors for interactive states
    bgFillTertiary: string;
    bgFillQuaternary: string;

    // Text colors
    textPrimary: string;
    textSecondary: string;
    textTertiary: string;
    textMuted: string;
    textInverse: string;
    textSelected: string; // High-contrast selection text

    // Border colors
    borderPrimary: string;
    borderSecondary: string;
    borderHover: string;

    // Input colors
    inputBg: string;
    inputBorder: string;

    // Iconography
    iconGrand: string;
    iconFork: string;
    iconSystem: string;

    // Button colors (theme-aware for proper contrast)
    buttonPrimary: string;
    buttonPrimaryHover: string;
    buttonPrimaryText: string;
  };

  // Spacing
  spacing: typeof DESIGN_TOKENS.SPACING;

  // Border radius
  borderRadius: typeof DESIGN_TOKENS.BORDER_RADIUS;

  // Typography
  fontFamily: typeof DESIGN_TOKENS.FONT_FAMILY;
  fontSize: typeof DESIGN_TOKENS.FONT_SIZE;
  fontWeight: typeof DESIGN_TOKENS.FONT_WEIGHT;
  lineHeight: typeof DESIGN_TOKENS.LINE_HEIGHT;
  letterSpacing: typeof DESIGN_TOKENS.LETTER_SPACING;

  // Dimensions
  dimensions: typeof DESIGN_TOKENS.DIMENSIONS;

  // Modal max heights
  modalMaxHeight: typeof DESIGN_TOKENS.MODAL_MAX_HEIGHT;

  // Overlays (theme-aware backdrop and content overlays)
  overlays: {
    backdrop: string;
    content: string;
    navActive: string;
  };

  // Z-index
  zIndex: typeof DESIGN_TOKENS.Z_INDEX;

  // Breakpoints
  breakpoints: typeof DESIGN_TOKENS.BREAKPOINTS;

  // Transitions
  transitions: typeof DESIGN_TOKENS.TRANSITIONS;
}

export type ThemeMode = 'light' | 'dark';

const sharedThemeValues = {
  spacing: DESIGN_TOKENS.SPACING,
  borderRadius: DESIGN_TOKENS.BORDER_RADIUS,
  fontFamily: DESIGN_TOKENS.FONT_FAMILY,
  fontSize: DESIGN_TOKENS.FONT_SIZE,
  fontWeight: DESIGN_TOKENS.FONT_WEIGHT,
  lineHeight: DESIGN_TOKENS.LINE_HEIGHT,
  letterSpacing: DESIGN_TOKENS.LETTER_SPACING,
  dimensions: DESIGN_TOKENS.DIMENSIONS,
  modalMaxHeight: DESIGN_TOKENS.MODAL_MAX_HEIGHT,
  zIndex: DESIGN_TOKENS.Z_INDEX,
  breakpoints: DESIGN_TOKENS.BREAKPOINTS,
  transitions: DESIGN_TOKENS.TRANSITIONS,
} as const;

const createTheme = (mode: ThemeMode): StyledTheme => {
  const colors = createColorTheme(mode);
  const isLight = mode === 'light';

  return {
    colors: {
      ...colors,
      // Explicitly include alpha variants for TypeScript
      primaryBg: (colors as any).primaryBg,
      // Additional computed colors not in base theme
      bgContainer: colors.bgPrimary,
      bgFillTertiary: 'transparent',
      bgFillQuaternary: 'transparent',
      inputBg: colors.bgPrimary,
      inputBorder: colors.borderSecondary,
      iconGrand: colors.primary,
      iconFork: colors.textSecondary, // Was secondary (medium gray)
      iconSystem: colors.textTertiary, // Was accent (light gray)
    },
    overlays: {
      backdrop: isLight
        ? DESIGN_TOKENS.OVERLAYS.BACKDROP_LIGHT
        : DESIGN_TOKENS.OVERLAYS.BACKDROP_DARK,
      content: isLight ? DESIGN_TOKENS.OVERLAYS.CONTENT_LIGHT : DESIGN_TOKENS.OVERLAYS.CONTENT_DARK,
      navActive: isLight
        ? DESIGN_TOKENS.OVERLAYS.NAV_ACTIVE_LIGHT
        : DESIGN_TOKENS.OVERLAYS.NAV_ACTIVE_DARK,
    },
    ...sharedThemeValues,
  };
};

export const lightTheme: StyledTheme = createTheme('light');
export const darkTheme: StyledTheme = createTheme('dark');
