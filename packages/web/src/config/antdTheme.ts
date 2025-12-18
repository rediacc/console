import { DESIGN_TOKENS } from '@/utils/styleConstants';
import {
  colorTokens,
  STATUS_COLORS,
  createColorTheme,
  createAlphaVariants,
} from '@/styles/colorSystem';
import type { ThemeConfig } from 'antd';

/**
 * Export colorTokens for backward compatibility
 * Now sourced from the unified colorSystem
 */
export { colorTokens };

/**
 * Shared Design Tokens (theme-independent)
 */
const RADIUS = { SM: 4, MD: 6, LG: 8, XL: 12 } as const;
const CONTROL_HEIGHT = 44; // Unified form control height

const sharedTokens = {
  borderRadius: RADIUS.MD,
  borderRadiusLG: RADIUS.LG,
  borderRadiusSM: RADIUS.SM,
  fontSize: DESIGN_TOKENS.FONT_SIZE.SM,
  fontSizeHeading1: DESIGN_TOKENS.FONT_SIZE.XXXXL,
  fontSizeHeading2: DESIGN_TOKENS.FONT_SIZE.XXXL,
  fontSizeHeading3: DESIGN_TOKENS.FONT_SIZE.XXL,
  fontSizeHeading4: DESIGN_TOKENS.FONT_SIZE.XL,
  fontSizeHeading5: DESIGN_TOKENS.FONT_SIZE.LG,
  fontSizeHeading6: DESIGN_TOKENS.FONT_SIZE.MD,
  lineHeight: DESIGN_TOKENS.LINE_HEIGHT.NORMAL,
  lineHeightHeading1: DESIGN_TOKENS.LINE_HEIGHT.TIGHT,
  lineHeightHeading2: DESIGN_TOKENS.LINE_HEIGHT.TIGHT,
  lineHeightHeading3: DESIGN_TOKENS.LINE_HEIGHT.NORMAL,
  lineHeightHeading4: DESIGN_TOKENS.LINE_HEIGHT.NORMAL,
  lineHeightHeading5: DESIGN_TOKENS.LINE_HEIGHT.NORMAL,
  lineHeightHeading6: DESIGN_TOKENS.LINE_HEIGHT.NORMAL,
  motionDurationSlow: '0.3s',
  motionDurationMid: '0.2s',
  motionDurationFast: '0.1s',
};

const baseControlTokens = {
  controlHeight: CONTROL_HEIGHT,
  borderRadius: RADIUS.MD,
};

const paddedControlTokens = {
  ...baseControlTokens,
  paddingBlock: 10,
  paddingInline: 14,
};

const focusStateTokens = (color: string) => ({
  hoverBorderColor: color,
  activeBorderColor: color,
});

const createButtonTokens = (theme: ReturnType<typeof createColorTheme>, primaryColor: string) => ({
  borderRadius: RADIUS.MD,
  paddingContentHorizontal: 16,
  paddingContentVertical: 8,
  defaultBorderColor: theme.borderPrimary,
  defaultColor: theme.textPrimary,
  defaultBg: theme.bgPrimary,
  defaultHoverBg: theme.bgPrimary,
  defaultHoverBorderColor: primaryColor,
  defaultHoverColor: theme.textPrimary,
  defaultActiveBg: theme.bgPrimary,
  defaultActiveBorderColor: primaryColor,
  defaultActiveColor: theme.textPrimary,
  primaryColor: theme.textInverse,
  textTextColor: theme.textPrimary,
  textTextHoverColor: theme.textSecondary,
  textTextActiveColor: theme.textPrimary,
  fontWeight: DESIGN_TOKENS.FONT_WEIGHT.SEMIBOLD,
  linkHoverBg: 'transparent',
  textHoverBg: theme.bgPrimary,
});

const createDropdownTokens = (theme: ReturnType<typeof createColorTheme>) => ({
  borderRadiusLG: RADIUS.LG,
  controlItemBgHover: theme.bgPrimary,
  controlItemBgActive: theme.bgPrimary,
});

const createPaginationTokens = (theme: ReturnType<typeof createColorTheme>) => ({
  borderRadius: RADIUS.MD,
  itemSize: 32,
  itemBg: theme.bgPrimary,
  itemLinkBg: theme.bgPrimary,
  itemInputBg: theme.bgPrimary,
  itemActiveBg: theme.bgPrimary,
  itemActiveColor: theme.textPrimary,
  itemActiveColorHover: theme.textPrimary,
  itemActiveBgDisabled: theme.bgPrimary,
  itemActiveColorDisabled: theme.textTertiary,
});

const createTabsTokens = (theme: ReturnType<typeof createColorTheme>) => ({
  cardBg: theme.bgPrimary,
  cardGutter: DESIGN_TOKENS.SPACING.XS,
  horizontalMargin: `0 0 ${DESIGN_TOKENS.SPACING.MD}px 0`,
  itemActiveColor: theme.textPrimary,
  itemHoverColor: theme.textSecondary,
  itemSelectedColor: theme.textPrimary,
  inkBarColor: theme.textPrimary,
});

const createMenuTokens = (theme: ReturnType<typeof createColorTheme>, primaryColor: string) => ({
  itemColor: theme.textPrimary,
  itemBg: 'transparent',
  itemSelectedBg: theme.bgPrimary,
  itemSelectedColor: theme.textPrimary,
  itemHoverBg: theme.bgPrimary,
  itemHoverColor: primaryColor,
  itemActiveBg: theme.bgPrimary,
  itemDisabledColor: theme.textMuted,
  horizontalItemHoverBg: 'transparent',
  iconSize: 16,
  itemHeight: CONTROL_HEIGHT,
  itemBorderRadius: RADIUS.MD,
});

/**
 * Component Configuration Factory
 */
const createComponentConfig = (isDark: boolean) => {
  const theme = createColorTheme(isDark ? 'dark' : 'light');
  const primaryColor = theme.primary;

  // Get alpha variants (now theme-aware)
  const alphas = createAlphaVariants(isDark ? 'dark' : 'light', 'primary');
  const primaryBg = (alphas as any).primaryBg;

  return {
    Input: {
      ...paddedControlTokens,
      controlHeightLG: CONTROL_HEIGHT,
      colorBorder: theme.borderPrimary,
      colorBgContainer: theme.bgPrimary,
      ...focusStateTokens(primaryColor),
    },
    InputNumber: {
      ...paddedControlTokens,
      ...focusStateTokens(primaryColor),
    },
    Select: {
      ...baseControlTokens,
      selectHeight: baseControlTokens.controlHeight,
      controlHeightSM: CONTROL_HEIGHT,
      colorBorder: theme.borderPrimary,
      colorBgContainer: theme.bgPrimary,
      optionSelectedBg: theme.bgPrimary,
      optionSelectedColor: theme.textPrimary,
      optionSelectedFontWeight: DESIGN_TOKENS.FONT_WEIGHT.SEMIBOLD,
      optionActiveBg: theme.bgPrimary,
      optionPadding: `${DESIGN_TOKENS.SPACING.SM}px ${DESIGN_TOKENS.SPACING.SM_LG}px`,
      optionFontSize: DESIGN_TOKENS.FONT_SIZE.SM,
      optionLineHeight: `${DESIGN_TOKENS.FONT_SIZE.XL}px`,
      optionHeight: DESIGN_TOKENS.DIMENSIONS.FORM_CONTROL_HEIGHT,
      controlOutline: primaryBg,
      selectorBg: theme.bgPrimary,
      clearBg: 'transparent',
      showArrowPaddingInlineEnd: 12,
      activeOutlineColor: primaryColor,
      ...focusStateTokens(primaryColor),
    },
    Button: createButtonTokens(theme, primaryColor),
    Card: {
      borderRadiusLG: RADIUS.LG,
      headerBg: 'transparent',
      headerFontSize: DESIGN_TOKENS.FONT_SIZE.MD,
      headerFontSizeSM: DESIGN_TOKENS.FONT_SIZE.SM,
    },
    Table: {
      borderRadius: RADIUS.MD,
      headerBg: theme.bgPrimary,
      headerColor: theme.textPrimary,
      rowHoverBg: theme.bgPrimary,
      rowSelectedBg: theme.bgPrimary,
      rowSelectedHoverBg: theme.bgPrimary,
      borderColor: theme.borderPrimary,
      headerSplitColor: theme.borderPrimary,
      footerBg: theme.bgPrimary,
      footerColor: theme.textSecondary,
      cellPaddingBlock: 12,
      cellPaddingInline: 16,
    },
    Modal: {
      borderRadiusLG: RADIUS.XL,
      headerBg: theme.bgPrimary,
      contentBg: theme.bgPrimary,
      footerBg: theme.bgPrimary,
      titleFontSize: DESIGN_TOKENS.FONT_SIZE.LG,
      titleLineHeight: DESIGN_TOKENS.LINE_HEIGHT.NORMAL,
      titleColor: theme.textPrimary,
      headerPadding: `${DESIGN_TOKENS.SPACING.MD}px ${DESIGN_TOKENS.SPACING.LG}px`,
      bodyPadding: DESIGN_TOKENS.SPACING.LG,
      footerPadding: `${DESIGN_TOKENS.SPACING.MD}px ${DESIGN_TOKENS.SPACING.LG}px`,
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
      borderRadiusLG: RADIUS.XL,
      footerPaddingBlock: 16,
      footerPaddingInline: 24,
    },
    Tabs: createTabsTokens(theme),
    Menu: createMenuTokens(theme, primaryColor),
    Dropdown: createDropdownTokens(theme),
    Pagination: createPaginationTokens(theme),
    Switch: {
      trackHeight: 22,
      trackMinWidth: 44,
      handleSize: 18,
      innerMinMargin: 4,
      innerMaxMargin: 24,
    },
    Checkbox: {
      borderRadiusSM: RADIUS.SM,
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
      cellHoverBg: theme.bgPrimary,
    },
    Form: {
      labelFontSize: DESIGN_TOKENS.FONT_SIZE.SM,
      labelColor: theme.textPrimary,
      labelRequiredMarkColor: STATUS_COLORS.error,
      labelHeight: DESIGN_TOKENS.DIMENSIONS.FORM_CONTROL_HEIGHT,
      verticalLabelPadding: `0 0 ${DESIGN_TOKENS.SPACING.SM}px`,
      verticalLabelMargin: '0',
      itemMarginBottom: DESIGN_TOKENS.SPACING.LG,
      inlineItemMarginBottom: DESIGN_TOKENS.SPACING.SM,
    },
    Alert: {
      borderRadiusLG: RADIUS.LG,
      withDescriptionPadding: DESIGN_TOKENS.SPACING.MD,
    },
    Badge: {
      dotSize: DESIGN_TOKENS.SPACING.SM,
      textFontSize: DESIGN_TOKENS.FONT_SIZE.XS,
      textFontWeight: DESIGN_TOKENS.FONT_WEIGHT.SEMIBOLD,
    },
    Tag: {
      borderRadiusSM: RADIUS.SM,
      defaultBg: theme.bgPrimary,
      defaultColor: theme.textPrimary,
      borderRadiusLG: RADIUS.MD,
      colorBorder: theme.borderPrimary,
    },
    Tooltip: {
      borderRadius: RADIUS.MD,
      colorBgSpotlight: theme.tooltipBg,
    },
    Popover: {
      borderRadiusLG: RADIUS.LG,
    },
    Message: {
      contentBg: theme.bgPrimary,
      borderRadiusLG: RADIUS.LG,
    },
    Notification: {
      borderRadiusLG: RADIUS.LG,
      width: 384,
    },
    Typography: {
      titleMarginBottom: '0.5em',
      titleMarginTop: '1.2em',
      fontSizeHeading1: DESIGN_TOKENS.FONT_SIZE.XXXXL,
      lineHeightHeading1: DESIGN_TOKENS.LINE_HEIGHT.TIGHT,
      fontWeightStrong: DESIGN_TOKENS.FONT_WEIGHT.BOLD,
      fontSizeHeading2: DESIGN_TOKENS.FONT_SIZE.XXXL,
      lineHeightHeading2: DESIGN_TOKENS.LINE_HEIGHT.TIGHT,
      fontSizeHeading3: DESIGN_TOKENS.FONT_SIZE.XXL,
      lineHeightHeading3: DESIGN_TOKENS.LINE_HEIGHT.NORMAL,
      fontSizeHeading4: DESIGN_TOKENS.FONT_SIZE.XL,
      lineHeightHeading4: DESIGN_TOKENS.LINE_HEIGHT.NORMAL,
      fontSizeHeading5: DESIGN_TOKENS.FONT_SIZE.LG,
      lineHeightHeading5: DESIGN_TOKENS.LINE_HEIGHT.NORMAL,
      fontSizeHeading6: DESIGN_TOKENS.FONT_SIZE.MD,
      lineHeightHeading6: DESIGN_TOKENS.LINE_HEIGHT.NORMAL,
    },
    Empty: {
      colorTextDescription: theme.textSecondary,
    },
    Statistic: {
      titleFontSize: DESIGN_TOKENS.FONT_SIZE.SM,
      contentFontSize: DESIGN_TOKENS.FONT_SIZE.XXL,
    },
    Progress: {
      defaultColor: primaryColor,
      remainingColor: theme.borderPrimary,
    },
    Timeline: {
      tailColor: theme.borderPrimary,
      dotBorderWidth: 2,
    },
    Segmented: {
      itemColor: theme.textSecondary,
      itemSelectedBg: theme.bgPrimary,
      itemSelectedColor: theme.textPrimary,
      itemHoverBg: theme.bgPrimary,
      itemHoverColor: theme.textPrimary,
      itemActiveBg: theme.bgPrimary,
      trackBg: theme.bgPrimary,
      trackPadding: `${DESIGN_TOKENS.SPACING.XXS}px`,
      borderRadius: RADIUS.MD,
    },
    Layout: {
      headerBg: theme.bgPrimary,
      headerColor: theme.textPrimary,
      headerHeight: 64,
      headerPadding: `0 ${DESIGN_TOKENS.SPACING.LG}px`,
      bodyBg: theme.bgPrimary,
      siderBg: theme.bgPrimary,
    },
  };
};

/**
 * Light Theme Configuration
 */
export const lightTheme: ThemeConfig = {
  token: {
    colorPrimary: colorTokens.light.primary,
    colorSuccess: STATUS_COLORS.success,
    colorWarning: STATUS_COLORS.warning,
    colorError: STATUS_COLORS.error,
    colorInfo: STATUS_COLORS.info,
    colorBgContainer: colorTokens.light.bgPrimary,
    colorBgElevated: colorTokens.light.bgPrimary,
    colorBgLayout: colorTokens.light.bgPrimary,
    colorText: colorTokens.light.textPrimary,
    colorTextSecondary: colorTokens.light.textSecondary,
    colorTextTertiary: colorTokens.light.textTertiary,
    colorBorder: colorTokens.light.borderPrimary,
    colorBorderSecondary: colorTokens.light.borderSecondary,
    ...sharedTokens,
  },
  components: createComponentConfig(false),
};

/**
 * Dark Theme Configuration
 */
export const darkTheme: ThemeConfig = {
  token: {
    colorPrimary: colorTokens.dark.primary,
    colorSuccess: STATUS_COLORS.success,
    colorWarning: STATUS_COLORS.warning,
    colorError: STATUS_COLORS.error,
    colorInfo: STATUS_COLORS.info,
    colorBgContainer: colorTokens.dark.bgPrimary,
    colorBgElevated: colorTokens.dark.bgPrimary,
    colorBgLayout: colorTokens.dark.bgPrimary,
    colorText: colorTokens.dark.textPrimary,
    colorTextSecondary: colorTokens.dark.textSecondary,
    colorTextTertiary: colorTokens.dark.textTertiary,
    colorBorder: colorTokens.dark.borderPrimary,
    colorBorderSecondary: colorTokens.dark.borderSecondary,
    ...sharedTokens,
  },
  components: createComponentConfig(true),
};
