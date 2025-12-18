/**
 * Color System - No Opacity
 * All colors are fully opaque solid colors
 * Visual hierarchy through distinct color values, not transparency
 */

/**
 * Base Colors (Black & White)
 */
const BASE_COLORS = {
  light: {
    surface: '#ffffff',
    overlay: '0, 0, 0', // Black RGB
    text: '#000000',
  },
  dark: {
    surface: '#000000',
    overlay: '255, 255, 255', // White RGB
    text: '#ffffff',
  },
} as const;

/**
 * Brand Colors - REMOVED
 * All colors are now derived from black/white + opacity
 * No discrete gray values needed
 */

/**
 * Status Colors (opacity-based except error)
 * Using opacity variations for semantic meaning
 * SHARPER VALUES for better distinction
 */
export const STATUS_COLORS = {
  success: '#404040', // Medium-dark gray
  warning: '#525252', // Medium gray
  error: '#dc3545', // Red (only color)
  info: '#333333', // Darkest gray
} as const;

/**
 * Theme mode type
 */
export type ThemeMode = 'light' | 'dark';

/**
 * Alpha Variant Generator
 * Creates shadow variants - backgrounds use pure white/black
 * Shadows use solid color fallback (no transparency)
 */
export const createAlphaVariants = (mode: ThemeMode, prefix: string): Record<string, string> => {
  const surface = mode === 'light' ? '#ffffff' : '#000000';
  const shadowColor = mode === 'light' ? '#d9d9d9' : '#1a1a1a'; // Solid color approximation
  return {
    [`${prefix}Bg`]: surface, // Pure white/black only
    [`${prefix}BgHover`]: surface, // Same - use transforms instead
    [`${prefix}BgActive`]: surface, // Same - use transforms instead
    [`${prefix}Shadow`]: `0 2px 8px ${shadowColor}`, // Solid shadow color
  };
};

/**
 * Theme Palette Generator
 * Creates all theme-specific colors (bg, text, border, button) based on mode
 * Uses solid colors for all hierarchy - NO transparency/opacity
 */
export const createThemePalette = (mode: ThemeMode) => {
  const base = BASE_COLORS[mode];

  return {
    // Primary colors (theme-aware)
    primary: base.text,
    primaryHover: base.text, // Same as primary now

    // Backgrounds (ALL use pure white/black - NO grays)
    bgPrimary: base.surface,
    bgSecondary: base.surface, // Same as bgPrimary - separation via borders
    bgTertiary: base.surface, // Same as bgPrimary - separation via borders
    bgHover: base.surface, // Same as bgPrimary - use transforms instead
    bgActive: base.surface, // Same as bgPrimary - use transforms instead
    bgSelected: base.surface, // Same as bgPrimary - use border accents

    // Text (solid colors for hierarchy - NO rgba)
    textPrimary: base.text,
    textSecondary: mode === 'light' ? '#404040' : '#bfbfbf', // ~75% brightness
    textTertiary: mode === 'light' ? '#666666' : '#999999', // ~60% brightness
    textMuted: mode === 'light' ? '#595959' : '#a6a6a6', // ~65% brightness
    textInverse: mode === 'light' ? '#ffffff' : '#000000',
    textSelected: base.text,

    // Borders (solid colors - NO rgba)
    borderPrimary: mode === 'light' ? '#d0d0d0' : '#404040', // ~25% brightness
    borderSecondary: mode === 'light' ? '#d0d0d0' : '#404040', // ~25% brightness
    borderHover: mode === 'light' ? '#999999' : '#666666', // ~40% brightness

    // Tooltip background
    tooltipBg: '#2a2a2a',

    // Button colors (same as primary now)
    buttonPrimary: base.text,
    buttonPrimaryHover: base.text,
    buttonPrimaryText: base.surface, // Inverse for contrast
  };
};

/**
 * Feedback Surface Generator
 * Creates background colors for status/feedback states
 * Now using pure white/black - colored accents via borders instead
 */
export const createFeedbackSurfaces = (mode: ThemeMode) => {
  const surface = mode === 'light' ? '#ffffff' : '#000000';

  return {
    bgSuccess: surface, // Pure white/black - use success border instead
    bgWarning: surface, // Pure white/black - use warning border instead
    bgError: surface, // Pure white/black - use error border instead
    bgInfo: surface, // Pure white/black - use info border instead
  };
};

/**
 * Complete Color Theme Factory
 * Single source of truth for all colors based on theme mode
 * Pure black & white with opacity-based hierarchy
 */
export const createColorTheme = (mode: ThemeMode) => {
  const palette = createThemePalette(mode);
  const feedback = createFeedbackSurfaces(mode);
  const primaryAlphas = createAlphaVariants(mode, 'primary');

  return {
    ...STATUS_COLORS,
    ...palette,
    ...feedback,
    ...primaryAlphas,
  };
};

/**
 * Color tokens export for backward compatibility with antdTheme.ts
 * Now uses opacity-based black & white system
 */
export const colorTokens = {
  ...STATUS_COLORS,
  // Alpha variants for light mode (primaryBg, primaryBgHover, etc.)
  ...createAlphaVariants('light', 'primary'),
  // Theme-specific palettes
  light: createThemePalette('light'),
  dark: createThemePalette('dark'),
};
