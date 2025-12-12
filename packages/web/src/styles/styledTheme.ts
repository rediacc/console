import { colorTokens } from '@/config/antdTheme';
import { DESIGN_TOKENS } from '@/utils/styleConstants';

export interface StyledTheme {
  // Colors
  colors: {
    primary: string;
    primaryHover: string;
    primaryBg: string;
    secondary: string;
    secondaryHover: string;
    accent: string;

    // Status colors
    success: string;
    warning: string;
    error: string;
    info: string;

    // Background colors
    bgPrimary: string;
    bgSecondary: string;
    bgTertiary: string;
    bgHover: string;
    bgActive: string;
    bgSelected: string; // High-contrast selection background
    bgSuccess: string;
    bgWarning: string;
    bgError: string;
    bgInfo: string;

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

    // Shadow colors
    shadow: string;
    shadowStrong: string;

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

  // Shadows (includes theme-aware computed values)
  shadows: typeof DESIGN_TOKENS.SHADOWS & {
    panel: string;
    controlHandle: string;
  };

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

type ThemeMode = 'light' | 'dark';

const feedbackSurfaces: Record<
  ThemeMode,
  { success: string; warning: string; error: string; info: string }
> = {
  light: {
    success: colorTokens.light.bgSecondary,
    warning: colorTokens.light.bgHover,
    error: `${colorTokens.error}14`,
    info: colorTokens.light.bgTertiary,
  },
  dark: {
    success: colorTokens.dark.bgTertiary,
    warning: colorTokens.dark.bgHover,
    error: `${colorTokens.error}33`,
    info: colorTokens.dark.bgSecondary,
  },
};

const sharedThemeValues = {
  spacing: DESIGN_TOKENS.SPACING,
  borderRadius: DESIGN_TOKENS.BORDER_RADIUS,
  fontFamily: DESIGN_TOKENS.FONT_FAMILY,
  fontSize: DESIGN_TOKENS.FONT_SIZE,
  fontWeight: DESIGN_TOKENS.FONT_WEIGHT,
  lineHeight: DESIGN_TOKENS.LINE_HEIGHT,
  letterSpacing: DESIGN_TOKENS.LETTER_SPACING,
  dimensions: DESIGN_TOKENS.DIMENSIONS,
  zIndex: DESIGN_TOKENS.Z_INDEX,
  breakpoints: DESIGN_TOKENS.BREAKPOINTS,
  transitions: DESIGN_TOKENS.TRANSITIONS,
} as const;

const createTheme = (mode: ThemeMode): StyledTheme => {
  const palette = colorTokens[mode];
  const feedback = feedbackSurfaces[mode];
  const isLight = mode === 'light';

  return {
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
      bgPrimary: palette.bgPrimary,
      bgSecondary: palette.bgSecondary,
      bgTertiary: palette.bgTertiary,
      bgHover: palette.bgHover,
      bgActive: palette.bgActive,
      bgSelected: palette.bgSelected,
      bgSuccess: feedback.success,
      bgWarning: feedback.warning,
      bgError: feedback.error,
      bgInfo: feedback.info,
      textPrimary: palette.textPrimary,
      textSecondary: palette.textSecondary,
      textTertiary: palette.textTertiary,
      textMuted: palette.textMuted,
      textInverse: palette.textInverse,
      textSelected: palette.textSelected,
      borderPrimary: palette.borderPrimary,
      borderSecondary: palette.borderSecondary,
      borderHover: palette.borderHover,
      shadow: palette.shadow,
      shadowStrong: isLight
        ? DESIGN_TOKENS.SHADOWS.SHADOW_STRONG_LIGHT
        : DESIGN_TOKENS.SHADOWS.SHADOW_STRONG_DARK,
      inputBg: isLight ? palette.bgPrimary : palette.bgSecondary,
      inputBorder: palette.borderSecondary,
      iconGrand: colorTokens.primary,
      iconFork: colorTokens.secondary,
      iconSystem: colorTokens.accent,
      buttonPrimary: palette.buttonPrimary,
      buttonPrimaryHover: palette.buttonPrimaryHover,
      buttonPrimaryText: palette.buttonPrimaryText,
    },
    shadows: {
      ...DESIGN_TOKENS.SHADOWS,
      panel: isLight ? DESIGN_TOKENS.SHADOWS.PANEL_LEFT : DESIGN_TOKENS.SHADOWS.PANEL_LEFT_DARK,
      controlHandle: isLight
        ? DESIGN_TOKENS.SHADOWS.CONTROL_HANDLE
        : DESIGN_TOKENS.SHADOWS.CONTROL_HANDLE_DARK,
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
