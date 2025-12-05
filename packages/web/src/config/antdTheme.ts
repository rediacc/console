import type { ThemeConfig } from 'antd';

/**
 * Brand Colors (theme-independent)
 * Grayscale palette with minimal red for errors only
 */
const brandColors = {
  primary: '#1a1a1a', // Dark gray
  primaryHover: '#0a0a0a', // Darker gray
  secondary: '#4a4a4a', // Medium gray
  secondaryHover: '#3a3a3a', // Darker medium gray
  accent: '#6a6a6a', // Light gray
  success: '#4a4a4a', // Gray (no green)
  warning: '#5a5a5a', // Gray (no orange)
  error: '#dc3545', // Red (only exception)
  info: '#6a6a6a', // Gray (no blue)
};

/**
 * Derived Colors (alpha variants)
 * All grayscale except error shadow
 */
const derivedColors = {
  primaryBg: 'rgba(26, 26, 26, 0.05)', // primary with low opacity
  primaryBgHover: 'rgba(26, 26, 26, 0.08)', // primary with slightly higher opacity
  primaryBgActive: 'rgba(26, 26, 26, 0.12)', // primary with medium opacity
  primaryShadow: '0 2px 8px rgba(0, 0, 0, 0.15)',

  accentBg: 'rgba(106, 106, 106, 0.1)', // accent with low opacity
  accentBgHover: 'rgba(106, 106, 106, 0.15)', // accent with medium opacity
  accentBgActive: 'rgba(106, 106, 106, 0.2)', // accent with higher opacity
  accentBgSelected: 'rgba(106, 106, 106, 0.2)',
  accentBgStrong: 'rgba(106, 106, 106, 0.25)',
  accentShadow: '0 2px 8px rgba(0, 0, 0, 0.2)',

  errorShadow: '0 2px 8px rgba(220, 53, 69, 0.15)', // Keep red for errors
};

/**
 * Theme-specific Colors
 */
const themeColors = {
  light: {
    bgPrimary: '#ffffff',
    bgSecondary: '#f8f9fa',
    bgTertiary: '#e9ecef',
    bgHover: '#f1f3f5',
    bgActive: '#e9ecef',
    bgSelected: '#e9ecef', // Subtle selected state for light theme
    textPrimary: '#1a1a1a',
    textSecondary: '#3d4852',
    textTertiary: '#5a6570',
    textMuted: '#9ca3af',
    textInverse: '#ffffff',
    textSelected: '#1a1a1a', // Dark text for selected states
    borderPrimary: '#dee2e6',
    borderSecondary: '#e9ecef',
    borderHover: '#adb5bd',
    shadow: 'rgba(0, 0, 0, 0.1)',
    shadowSm: '0 1px 3px rgba(0, 0, 0, 0.1)',
    shadowMd: '0 4px 12px rgba(0, 0, 0, 0.15)',
    shadowLg: '0 6px 16px rgba(0, 0, 0, 0.12)',
    tooltipBg: 'rgba(0, 0, 0, 0.85)',
  },
  dark: {
    bgPrimary: '#0a0a0a',
    bgSecondary: '#1a1a1a',
    bgTertiary: '#2a2a2a',
    bgHover: '#2d2d2d',
    bgActive: '#3a3a3a',
    bgSelected: '#4a4a4a', // Medium-light gray for selected states (not inverted)
    textPrimary: '#fafafa',
    textSecondary: '#e5e7eb',
    textTertiary: '#d1d5db',
    textMuted: '#9ca3af',
    textInverse: '#1a1a1a',
    textSelected: '#ffffff', // White text for selected states
    borderPrimary: '#27272a',
    borderSecondary: '#3f3f46',
    borderHover: '#52525b',
    shadow: 'rgba(0, 0, 0, 0.3)',
    shadowSm: '0 1px 3px rgba(0, 0, 0, 0.3)',
    shadowMd: '0 4px 12px rgba(0, 0, 0, 0.4)',
    shadowLg: '0 6px 16px rgba(0, 0, 0, 0.4)',
    tooltipBg: 'rgba(0, 0, 0, 0.95)',
  },
};

/**
 * Export for GlobalStyles and styled-components
 */
export const colorTokens = {
  ...brandColors,
  ...derivedColors,
  light: themeColors.light,
  dark: themeColors.dark,
};

/**
 * Shared Design Tokens (theme-independent)
 */
const sharedTokens = {
  borderRadius: 6,
  borderRadiusLG: 8,
  borderRadiusSM: 4,
  fontSize: 14,
  fontSizeHeading1: 38,
  fontSizeHeading2: 30,
  fontSizeHeading3: 24,
  fontSizeHeading4: 20,
  fontSizeHeading5: 16,
  lineHeight: 1.5715,
  lineHeightHeading1: 1.21,
  lineHeightHeading2: 1.27,
  lineHeightHeading3: 1.33,
  lineHeightHeading4: 1.4,
  lineHeightHeading5: 1.5,
  motionDurationSlow: '0.3s',
  motionDurationMid: '0.2s',
  motionDurationFast: '0.1s',
};

const baseControlTokens = {
  controlHeight: 44,
  borderRadius: 6,
};

const paddedControlTokens = {
  ...baseControlTokens,
  paddingBlock: 10,
  paddingInline: 14,
};

const focusStateTokens = (color: string) => ({
  activeShadow: `0 0 0 1px ${color}`,
  hoverBorderColor: color,
  activeBorderColor: color,
});

const createButtonTokens = (
  theme: typeof themeColors.light,
  primaryColor: string,
  primaryShadow: string
) => ({
  borderRadius: 6,
  paddingContentHorizontal: 16,
  paddingContentVertical: 8,
  primaryShadow,
  dangerShadow: derivedColors.errorShadow,
  defaultShadow: theme.shadowSm,
  defaultBorderColor: theme.borderPrimary,
  defaultColor: theme.textPrimary,
  defaultBg: theme.bgPrimary,
  defaultHoverBg: theme.bgSecondary,
  defaultHoverBorderColor: primaryColor,
  defaultHoverColor: theme.textPrimary,
  defaultActiveBg: theme.bgActive,
  defaultActiveBorderColor: primaryColor,
  defaultActiveColor: theme.textPrimary,
  primaryColor: theme.textInverse,
  textTextColor: theme.textPrimary,
  textTextHoverColor: theme.textSecondary,
  textTextActiveColor: theme.textPrimary,
  fontWeight: 600,
  linkHoverBg: 'transparent',
  textHoverBg: theme.bgHover,
});

const createDropdownTokens = (theme: typeof themeColors.light, hoverBg: string) => ({
  borderRadiusLG: 8,
  controlItemBgHover: hoverBg,
  controlItemBgActive: theme.bgSelected,
  boxShadowSecondary: theme.shadowMd,
});

const createPaginationTokens = (theme: typeof themeColors.light) => ({
  borderRadius: 6,
  itemSize: 32,
  itemBg: theme.bgPrimary,
  itemLinkBg: theme.bgPrimary,
  itemInputBg: theme.bgPrimary,
  itemActiveBg: theme.bgSelected,
  itemActiveColor: theme.textSelected,
  itemActiveColorHover: theme.textSelected,
  itemActiveBgDisabled: theme.bgSecondary,
  itemActiveColorDisabled: theme.textTertiary,
});

const createTabsTokens = (theme: typeof themeColors.light) => ({
  cardBg: theme.bgPrimary,
  cardGutter: 4,
  horizontalMargin: '0 0 16px 0',
  itemActiveColor: theme.textPrimary,
  itemHoverColor: theme.textSecondary,
  itemSelectedColor: theme.textPrimary,
  inkBarColor: theme.textPrimary,
});

const createMenuTokens = (
  theme: typeof themeColors.light,
  primaryBgHover: string,
  primaryBgActive: string,
  primaryColor: string
) => ({
  itemColor: theme.textPrimary,
  itemBg: 'transparent',
  itemSelectedBg: theme.bgSelected,
  itemSelectedColor: theme.textSelected,
  itemHoverBg: primaryBgHover,
  itemHoverColor: primaryColor,
  itemActiveBg: primaryBgActive,
  itemDisabledColor: theme.textMuted,
  horizontalItemHoverBg: 'transparent',
  iconSize: 16,
  itemHeight: 44,
  itemBorderRadius: 6,
});

/**
 * Component Configuration Factory
 */
const createComponentConfig = (isDark: boolean) => {
  const theme = isDark ? themeColors.dark : themeColors.light;
  const primaryColor = isDark ? brandColors.accent : brandColors.primary;
  const primaryBg = isDark ? derivedColors.accentBg : derivedColors.primaryBg;
  const primaryBgHover = isDark ? derivedColors.accentBgHover : derivedColors.primaryBgHover;
  const primaryBgActive = isDark ? derivedColors.accentBgActive : derivedColors.primaryBgActive;
  const primaryShadow = isDark ? derivedColors.accentShadow : derivedColors.primaryShadow;

  return {
    Input: {
      ...paddedControlTokens,
      controlHeightLG: 48,
      colorBorder: theme.borderPrimary,
      colorBgContainer: theme.bgPrimary,
      errorActiveShadow: `0 0 0 1px ${brandColors.error}`,
      ...focusStateTokens(primaryColor),
    },
    InputNumber: {
      ...paddedControlTokens,
      ...focusStateTokens(primaryColor),
    },
    Select: {
      ...baseControlTokens,
      selectHeight: baseControlTokens.controlHeight,
      controlHeightSM: 32,
      colorBorder: theme.borderPrimary,
      colorBgContainer: theme.bgPrimary,
      optionSelectedBg: theme.bgSelected,
      optionSelectedColor: theme.textSelected,
      optionSelectedFontWeight: 600,
      optionActiveBg: primaryBgHover,
      optionPadding: '8px 12px',
      optionFontSize: 14,
      optionLineHeight: '20px',
      optionHeight: 40,
      controlOutline: primaryBg,
      selectorBg: theme.bgPrimary,
      clearBg: 'transparent',
      showArrowPaddingInlineEnd: 12,
      activeOutlineColor: primaryColor,
      ...focusStateTokens(primaryColor),
    },
    Button: createButtonTokens(theme, primaryColor, primaryShadow),
    Card: {
      borderRadiusLG: 8,
      boxShadowTertiary: theme.shadowSm,
      headerBg: 'transparent',
      headerFontSize: 16,
      headerFontSizeSM: 14,
    },
    Table: {
      borderRadius: 6,
      headerBg: theme.bgSecondary,
      headerColor: theme.textPrimary,
      rowHoverBg: primaryBgHover,
      rowSelectedBg: theme.bgSelected,
      rowSelectedHoverBg: theme.bgActive,
      borderColor: theme.borderSecondary,
      headerSplitColor: theme.borderSecondary,
      footerBg: theme.bgSecondary,
      footerColor: theme.textSecondary,
      cellPaddingBlock: 12,
      cellPaddingInline: 16,
    },
    Modal: {
      borderRadiusLG: 12,
      boxShadow: theme.shadowLg,
      headerBg: theme.bgPrimary,
      contentBg: theme.bgPrimary,
      footerBg: theme.bgPrimary,
      titleFontSize: 18,
      titleLineHeight: 1.5,
      titleColor: theme.textPrimary,
      headerPadding: '16px 24px',
      bodyPadding: 24,
      footerPadding: '16px 24px',
      headerBorderBottom: `1px solid ${theme.borderSecondary}`,
      footerBorderTop: `1px solid ${theme.borderSecondary}`,
      widthSM: 480,
      widthMD: 720,
      widthLG: 960,
      widthXL: 1280,
      maxHeight: '90vh',
      motionDurationSlow: '0.3s',
      motionDurationMid: '0.2s',
    },
    Drawer: {
      borderRadiusLG: 12,
      footerPaddingBlock: 16,
      footerPaddingInline: 24,
    },
    Tabs: createTabsTokens(theme),
    Menu: createMenuTokens(theme, primaryBgHover, primaryBgActive, primaryColor),
    Dropdown: createDropdownTokens(theme, primaryBgHover),
    Pagination: createPaginationTokens(theme),
    Switch: {
      trackHeight: 22,
      trackMinWidth: 44,
      handleSize: 18,
      innerMinMargin: 4,
      innerMaxMargin: 24,
    },
    Checkbox: {
      borderRadiusSM: 4,
      controlInteractiveSize: 18,
    },
    Radio: {
      dotSize: 10,
      radioSize: 18,
    },
    DatePicker: {
      ...baseControlTokens,
      ...focusStateTokens(primaryColor),
      cellActiveWithRangeBg: primaryBg,
      cellHoverBg: primaryBgHover,
    },
    Form: {
      labelFontSize: 14,
      labelColor: theme.textPrimary,
      labelRequiredMarkColor: brandColors.error,
      labelHeight: 32,
      verticalLabelPadding: '0 0 8px',
      verticalLabelMargin: '0',
      itemMarginBottom: 24,
      inlineItemMarginBottom: 8,
    },
    Alert: {
      borderRadiusLG: 8,
      withDescriptionPadding: 16,
    },
    Badge: {
      dotSize: 8,
      textFontSize: 12,
      textFontWeight: 600,
    },
    Tag: {
      borderRadiusSM: 4,
      defaultBg: theme.bgSecondary,
      defaultColor: theme.textPrimary,
    },
    Tooltip: {
      borderRadius: 6,
      colorBgSpotlight: theme.tooltipBg,
    },
    Popover: {
      borderRadiusLG: 8,
      boxShadowSecondary: theme.shadowMd,
    },
    Message: {
      contentBg: theme.bgPrimary,
      borderRadiusLG: 8,
    },
    Notification: {
      borderRadiusLG: 8,
      width: 384,
    },
    Typography: {
      titleMarginBottom: '0.5em',
      titleMarginTop: '1.2em',
      // H1
      fontSizeHeading1: 36,
      lineHeightHeading1: 1.25,
      fontWeightStrong: 700,
      // H2
      fontSizeHeading2: 30,
      lineHeightHeading2: 1.25,
      // H3
      fontSizeHeading3: 24,
      lineHeightHeading3: 1.5,
      // H4
      fontSizeHeading4: 20,
      lineHeightHeading4: 1.5,
      // H5
      fontSizeHeading5: 18,
      lineHeightHeading5: 1.5,
    },
    Empty: {
      colorTextDescription: theme.textSecondary,
    },
    Statistic: {
      titleFontSize: 14,
      contentFontSize: 24,
    },
    Progress: {
      defaultColor: primaryColor,
      remainingColor: theme.bgTertiary,
    },
    Timeline: {
      tailColor: theme.borderPrimary,
      dotBorderWidth: 2,
    },
    Segmented: {
      itemColor: theme.textSecondary,
      itemSelectedBg: theme.bgPrimary,
      itemSelectedColor: theme.textPrimary,
      itemHoverBg: theme.bgHover,
      itemHoverColor: theme.textPrimary,
      itemActiveBg: theme.bgActive,
      trackBg: theme.bgTertiary,
      trackPadding: '2px',
      borderRadius: 6,
    },
    Layout: {
      headerBg: theme.bgSecondary,
      headerColor: theme.textPrimary,
      headerHeight: 64,
      headerPadding: '0 24px',
      bodyBg: theme.bgPrimary,
      siderBg: theme.bgSecondary,
    },
  };
};

/**
 * Light Theme Configuration
 */
export const lightTheme: ThemeConfig = {
  token: {
    colorPrimary: brandColors.primary,
    colorSuccess: brandColors.success,
    colorWarning: brandColors.warning,
    colorError: brandColors.error,
    colorInfo: brandColors.info,
    colorBgContainer: themeColors.light.bgPrimary,
    colorBgElevated: themeColors.light.bgPrimary,
    colorBgLayout: themeColors.light.bgSecondary,
    colorText: themeColors.light.textPrimary,
    colorTextSecondary: themeColors.light.textSecondary,
    colorTextTertiary: themeColors.light.textTertiary,
    colorBorder: themeColors.light.borderPrimary,
    colorBorderSecondary: themeColors.light.borderSecondary,
    ...sharedTokens,
  },
  components: createComponentConfig(false),
};

/**
 * Dark Theme Configuration
 */
export const darkTheme: ThemeConfig = {
  token: {
    colorPrimary: brandColors.accent,
    colorSuccess: brandColors.success,
    colorWarning: brandColors.warning,
    colorError: brandColors.error,
    colorInfo: brandColors.info,
    colorBgContainer: themeColors.dark.bgSecondary,
    colorBgElevated: themeColors.dark.bgTertiary,
    colorBgLayout: themeColors.dark.bgPrimary,
    colorText: themeColors.dark.textPrimary,
    colorTextSecondary: themeColors.dark.textSecondary,
    colorTextTertiary: themeColors.dark.textTertiary,
    colorBorder: themeColors.dark.borderPrimary,
    colorBorderSecondary: themeColors.dark.borderSecondary,
    ...sharedTokens,
  },
  components: createComponentConfig(true),
};
