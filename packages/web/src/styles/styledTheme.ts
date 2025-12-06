import { DESIGN_TOKENS } from '@/utils/styleConstants';
import { colorTokens } from '@/config/antdTheme';

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
  fontSize: typeof DESIGN_TOKENS.FONT_SIZE;
  fontWeight: typeof DESIGN_TOKENS.FONT_WEIGHT;
  lineHeight: typeof DESIGN_TOKENS.LINE_HEIGHT;
  letterSpacing: typeof DESIGN_TOKENS.LETTER_SPACING;

  // Dimensions
  dimensions: typeof DESIGN_TOKENS.DIMENSIONS;

  // Shadows
  shadows: typeof DESIGN_TOKENS.SHADOWS;

  // Z-index
  zIndex: typeof DESIGN_TOKENS.Z_INDEX;

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
  fontSize: DESIGN_TOKENS.FONT_SIZE,
  fontWeight: DESIGN_TOKENS.FONT_WEIGHT,
  lineHeight: DESIGN_TOKENS.LINE_HEIGHT,
  letterSpacing: DESIGN_TOKENS.LETTER_SPACING,
  dimensions: DESIGN_TOKENS.DIMENSIONS,
  shadows: DESIGN_TOKENS.SHADOWS,
  zIndex: DESIGN_TOKENS.Z_INDEX,
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
      shadowStrong: isLight ? 'rgba(0, 0, 0, 0.15)' : 'rgba(0, 0, 0, 0.5)',
      inputBg: isLight ? palette.bgPrimary : palette.bgSecondary,
      inputBorder: palette.borderSecondary,
      iconGrand: colorTokens.primary,
      iconFork: colorTokens.secondary,
      iconSystem: colorTokens.accent,
      buttonPrimary: palette.buttonPrimary,
      buttonPrimaryHover: palette.buttonPrimaryHover,
      buttonPrimaryText: palette.buttonPrimaryText,
    },
    ...sharedThemeValues,
  };
};

export const lightTheme: StyledTheme = createTheme('light');
export const darkTheme: StyledTheme = createTheme('dark');
