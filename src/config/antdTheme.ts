import type { ThemeConfig } from 'antd'

/**
 * Brand Colors (theme-independent)
 */
const brandColors = {
  primary: '#556b2f',
  primaryHover: '#4c6029',
  secondary: '#808000',
  secondaryHover: '#6e6e00',
  accent: '#7d9b49',
  success: '#28a745',
  warning: '#fd7e14',
  error: '#dc3545',
  info: '#007bff',
}

/**
 * Derived Colors (alpha variants)
 */
const derivedColors = {
  primaryBg: 'rgba(85, 107, 47, 0.1)',
  primaryBgHover: 'rgba(85, 107, 47, 0.05)',
  primaryBgActive: 'rgba(85, 107, 47, 0.15)',
  primaryShadow: '0 2px 8px rgba(85, 107, 47, 0.15)',
  
  accentBg: 'rgba(125, 155, 73, 0.1)',
  accentBgHover: 'rgba(125, 155, 73, 0.1)',
  accentBgActive: 'rgba(125, 155, 73, 0.2)',
  accentBgSelected: 'rgba(125, 155, 73, 0.2)',
  accentBgStrong: 'rgba(125, 155, 73, 0.25)',
  accentShadow: '0 2px 8px rgba(125, 155, 73, 0.2)',
  
  errorShadow: '0 2px 8px rgba(220, 53, 69, 0.15)',
}

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
    textPrimary: '#1a1a1a',
    textSecondary: '#3d4852',
    textTertiary: '#5a6570',
    textMuted: '#9ca3af',
    textInverse: '#ffffff',
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
    textPrimary: '#fafafa',
    textSecondary: '#e5e7eb',
    textTertiary: '#d1d5db',
    textMuted: '#9ca3af',
    textInverse: '#1a1a1a',
    borderPrimary: '#27272a',
    borderSecondary: '#3f3f46',
    borderHover: '#52525b',
    shadow: 'rgba(0, 0, 0, 0.3)',
    shadowSm: '0 1px 3px rgba(0, 0, 0, 0.3)',
    shadowMd: '0 4px 12px rgba(0, 0, 0, 0.4)',
    shadowLg: '0 6px 16px rgba(0, 0, 0, 0.4)',
    tooltipBg: 'rgba(0, 0, 0, 0.95)',
  },
}

/**
 * Export for GlobalStyles and styled-components
 */
export const colorTokens = {
  ...brandColors,
  ...derivedColors,
  light: themeColors.light,
  dark: themeColors.dark,
}

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
}

/**
 * Component Configuration Factory
 */
const createComponentConfig = (isDark: boolean) => {
  const theme = isDark ? themeColors.dark : themeColors.light
  const primaryColor = isDark ? brandColors.accent : brandColors.primary
  const primaryBg = isDark ? derivedColors.accentBg : derivedColors.primaryBg
  const primaryBgHover = isDark ? derivedColors.accentBgHover : derivedColors.primaryBgHover
  const primaryBgActive = isDark ? derivedColors.accentBgActive : derivedColors.primaryBgActive
  const primaryBgSelected = isDark ? derivedColors.accentBgSelected : derivedColors.primaryBg
  const primaryShadow = isDark ? derivedColors.accentShadow : derivedColors.primaryShadow
  
  return {
    Input: {
      controlHeight: 44,
      controlHeightLG: 48,
      borderRadius: 6,
      paddingBlock: 10,
      paddingInline: 14,
      colorBorder: theme.borderPrimary,
      colorBgContainer: theme.bgPrimary,
      activeShadow: `0 0 0 1px ${primaryColor}`,
      errorActiveShadow: `0 0 0 1px ${brandColors.error}`,
      hoverBorderColor: primaryColor,
      activeBorderColor: primaryColor,
    },
    InputNumber: {
      controlHeight: 44,
      borderRadius: 6,
      paddingBlock: 10,
      paddingInline: 14,
      activeShadow: `0 0 0 1px ${primaryColor}`,
      hoverBorderColor: primaryColor,
    },
    Select: {
      controlHeight: 44,
      borderRadius: 6,
      colorBorder: theme.borderPrimary,
      colorBgContainer: theme.bgPrimary,
      optionSelectedBg: primaryBg,
      optionActiveBg: primaryBgHover,
      controlOutline: primaryBg,
      selectorBg: theme.bgPrimary,
    },
    Button: {
      controlHeight: 44,
      controlHeightLG: 48,
      borderRadius: 6,
      paddingContentHorizontal: 16,
      paddingContentVertical: 8,
      primaryShadow: primaryShadow,
      dangerShadow: derivedColors.errorShadow,
      defaultBorderColor: theme.borderPrimary,
      defaultColor: theme.textPrimary,
      fontWeight: 600,
      // Link button specific
      linkHoverBg: 'transparent',
      textHoverBg: theme.bgHover,
    },
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
      borderColor: theme.borderSecondary,
      headerSplitColor: theme.borderSecondary,
      footerBg: theme.bgSecondary,
      cellPaddingBlock: 12,
      cellPaddingInline: 16,
    },
    Modal: {
      borderRadiusLG: 12,
      boxShadow: theme.shadowLg,
      headerBg: 'transparent',
      titleFontSize: 18,
      titleLineHeight: 1.5,
    },
    Drawer: {
      borderRadiusLG: 12,
      footerPaddingBlock: 16,
      footerPaddingInline: 24,
    },
    Tabs: {
      cardBg: theme.bgPrimary,
      cardGutter: 4,
      horizontalMargin: '0 0 16px 0',
      itemActiveColor: primaryColor,
      itemHoverColor: primaryColor,
      itemSelectedColor: primaryColor,
      inkBarColor: primaryColor,
    },
    Menu: {
      itemBg: 'transparent',
      itemSelectedBg: primaryBgSelected,
      itemSelectedColor: primaryColor,
      itemHoverBg: primaryBgHover,
      itemHoverColor: primaryColor,
      itemActiveBg: primaryBgActive,
      iconSize: 16,
      itemHeight: 44,
      itemBorderRadius: 6,
    },
    Dropdown: {
      borderRadiusLG: 8,
      controlItemBgHover: primaryBgHover,
      controlItemBgActive: primaryBg,
      boxShadowSecondary: theme.shadowMd,
    },
    Pagination: {
      itemActiveBg: primaryColor,
      itemLinkBg: theme.bgPrimary,
      itemBg: theme.bgPrimary,
      itemSize: 32,
      borderRadius: 6,
    },
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
      controlHeight: 44,
      borderRadius: 6,
      activeShadow: `0 0 0 1px ${primaryColor}`,
      hoverBorderColor: primaryColor,
      cellActiveWithRangeBg: primaryBg,
      cellHoverBg: primaryBgHover,
    },
    Form: {
      labelFontSize: 14,
      labelColor: theme.textPrimary,
      labelHeight: 32,
      verticalLabelPadding: '0 0 8px',
      itemMarginBottom: 24,
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
      itemSelectedBg: theme.bgPrimary,
      itemSelectedColor: theme.textPrimary,
      itemHoverBg: theme.bgHover,
      itemHoverColor: theme.textPrimary,
      trackBg: theme.bgTertiary,
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
  }
}

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
}

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
}
