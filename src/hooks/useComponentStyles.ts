import { useMemo } from 'react'
import { useTheme } from '@/context/ThemeContext'
import {
  DESIGN_TOKENS,
  createTouchTargetStyle,
  createCardStyle,
  createModalStyle,
  createInputStyle,
  createButtonStyle,
  createTypographyStyle,
  spacing,
  borderRadius,
  fontSize,
  fontWeight,
} from '@/utils/styleConstants'

export const useComponentStyles = () => {
  const { theme } = useTheme()

  return useMemo(() => ({
    // Touch targets
    touchTarget: createTouchTargetStyle(),
    touchTargetLarge: createTouchTargetStyle(DESIGN_TOKENS.TOUCH_TARGET.LARGE),
    touchTargetSmall: createTouchTargetStyle(DESIGN_TOKENS.TOUCH_TARGET.SMALL),

    // Cards and modals
    card: createCardStyle(),
    cardLarge: createCardStyle(DESIGN_TOKENS.DIMENSIONS.CARD_WIDTH_LG),
    modal: createModalStyle(),
    modalLarge: createModalStyle(DESIGN_TOKENS.DIMENSIONS.MODAL_WIDTH_LG),
    modalXLarge: createModalStyle(DESIGN_TOKENS.DIMENSIONS.MODAL_WIDTH_XL),

    // Form elements
    input: createInputStyle(),
    inputSmall: createInputStyle(DESIGN_TOKENS.DIMENSIONS.INPUT_HEIGHT_SM),
    inputLarge: createInputStyle(DESIGN_TOKENS.DIMENSIONS.INPUT_HEIGHT_LG),

    // Buttons
    buttonPrimary: createButtonStyle('primary'),
    buttonSecondary: createButtonStyle('secondary'),
    buttonGhost: createButtonStyle('ghost'),

    // Typography (matching style-guide.md)
    heading1: createTypographyStyle('H1', 'BOLD', 'TIGHT'),
    heading2: createTypographyStyle('H2', 'SEMIBOLD', 'TIGHT'),
    heading3: createTypographyStyle('H3', 'SEMIBOLD', 'NORMAL'),
    heading4: createTypographyStyle('H4', 'SEMIBOLD', 'NORMAL'),
    heading5: createTypographyStyle('H5', 'MEDIUM', 'NORMAL'),
    heading6: createTypographyStyle('BASE', 'MEDIUM', 'NORMAL'),
    bodyLarge: createTypographyStyle('LG', 'REGULAR', 'RELAXED'),
    body: createTypographyStyle('BASE', 'REGULAR', 'NORMAL'),
    bodySmall: createTypographyStyle('SM', 'REGULAR', 'NORMAL'),
    caption: createTypographyStyle('CAPTION', 'REGULAR', 'NORMAL'),
    label: createTypographyStyle('SM', 'MEDIUM', 'NORMAL'),

    // Layout
    container: {
      padding: spacing('CONTAINER'),
      maxWidth: '100%',
    },
    section: {
      marginBottom: spacing('XL'),
    },
    spacer: {
      margin: spacing('MD'),
    },

    // Flexbox utilities
    flexCenter: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
    },
    flexBetween: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
    },
    flexStart: {
      display: 'flex',
      alignItems: 'flex-start',
    },
    flexEnd: {
      display: 'flex',
      alignItems: 'flex-end',
    },
    flexColumn: {
      display: 'flex',
      flexDirection: 'column',
    },

    // Common spacing patterns
    marginBottom: {
      xs: { marginBottom: spacing('XS') },
      sm: { marginBottom: spacing('SM') },
      md: { marginBottom: spacing('MD') },
      lg: { marginBottom: spacing('LG') },
      xl: { marginBottom: spacing('XL') },
    },
    padding: {
      xs: { padding: spacing('XS') },
      sm: { padding: spacing('SM') },
      md: { padding: spacing('MD') },
      lg: { padding: spacing('LG') },
      xl: { padding: spacing('XL') },
    },

    // Theme-aware styles
    sidebar: {
      width: DESIGN_TOKENS.DIMENSIONS.SIDEBAR_WIDTH,
      boxShadow: theme === 'dark' ? DESIGN_TOKENS.SHADOWS.SIDEBAR_DARK : DESIGN_TOKENS.SHADOWS.SIDEBAR,
      background: 'var(--color-bg-container)',
      borderRight: '1px solid var(--color-border-secondary)',
    },
    header: {
      height: DESIGN_TOKENS.DIMENSIONS.HEADER_HEIGHT,
      boxShadow: theme === 'dark' ? DESIGN_TOKENS.SHADOWS.HEADER_DARK : DESIGN_TOKENS.SHADOWS.HEADER,
      background: 'var(--color-bg-container)',
      borderBottom: '1px solid var(--color-border-secondary)',
    },

    // Icon styles
    icon: {
      small: { fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_SM },
      medium: { fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_MD },
      large: { fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_LG },
      xlarge: { fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_XL },
      xxlarge: { fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_XXL },
      xxxlarge: { fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_XXXL },
    },

    // Error states
    errorField: {
      borderColor: 'var(--color-error)',
      boxShadow: DESIGN_TOKENS.SHADOWS.ERROR_FIELD,
    },
    errorMessage: {
      ...createTypographyStyle('XS', 'NORMAL', 'NORMAL'),
      color: 'var(--color-error)',
      marginTop: spacing('XS'),
    },

    // Loading states
    loading: {
      opacity: 0.6,
      pointerEvents: 'none' as const,
      transition: DESIGN_TOKENS.TRANSITIONS.DEFAULT,
    },

    // Hover effects
    hoverEffect: {
      transition: DESIGN_TOKENS.TRANSITIONS.HOVER,
      '&:hover': {
        transform: 'translateY(-1px)',
        boxShadow: DESIGN_TOKENS.SHADOWS.MD,
      },
    },

    // Focus styles for accessibility
    focusVisible: {
      outline: '2px solid var(--color-primary)',
      outlineOffset: '2px',
      borderRadius: borderRadius('SM'),
    },

    // Screen reader only content
    srOnly: {
      position: 'absolute' as const,
      width: '1px',
      height: '1px',
      padding: 0,
      margin: '-1px',
      overflow: 'hidden',
      clip: 'rect(0, 0, 0, 0)',
      whiteSpace: 'nowrap' as const,
      border: 0,
    },
  }), [theme])
}

// Specialized hooks for specific component types
export const useFormStyles = () => {
  const baseStyles = useComponentStyles()
  
  return useMemo(() => ({
    ...baseStyles,
    
    formGroup: {
      marginBottom: spacing('LG'),
    },
    
    formLabel: {
      ...createTypographyStyle('SM', 'MEDIUM', 'NORMAL'),
      color: 'var(--color-text-primary)',
      marginBottom: spacing('XS'),
      display: 'block',
    },
    
    formInput: {
      ...baseStyles.input,
      '&:focus': {
        ...baseStyles.focusVisible,
        borderColor: 'var(--color-primary)',
      },
    },
    
    formError: {
      ...baseStyles.errorMessage,
      display: 'flex',
      alignItems: 'center',
      gap: spacing('XS'),
    },
    
    formHelper: {
      ...createTypographyStyle('XS', 'NORMAL', 'NORMAL'),
      color: 'var(--color-text-secondary)',
      marginTop: spacing('XS'),
    },
    
    fieldset: {
      border: '1px solid var(--color-border-secondary)',
      borderRadius: borderRadius('LG'),
      padding: spacing('MD'),
      marginBottom: spacing('LG'),
    },
    
    legend: {
      ...createTypographyStyle('SM', 'MEDIUM', 'NORMAL'),
      color: 'var(--color-text-primary)',
      padding: `0 ${spacing('SM')}px`,
    },
  }), [baseStyles])
}

export const useTableStyles = () => {
  const baseStyles = useComponentStyles()
  
  return useMemo(() => ({
    ...baseStyles,
    
    tableContainer: {
      overflow: 'auto',
      borderRadius: borderRadius('LG'),
      border: '1px solid var(--color-border-secondary)',
    },
    
    tableHeader: {
      background: 'var(--color-fill-quaternary)',
      fontWeight: fontWeight('MEDIUM'),
      fontSize: fontSize('SM'),
    },
    
    tableCell: {
      padding: spacing('SM'),
      fontSize: fontSize('SM'),
      lineHeight: DESIGN_TOKENS.LINE_HEIGHT.NORMAL,
    },
    
    tableActionButton: {
      ...createTouchTargetStyle(DESIGN_TOKENS.TOUCH_TARGET.SMALL),
      borderRadius: borderRadius('SM'),
      border: 'none',
      background: 'transparent',
      cursor: 'pointer',
      transition: DESIGN_TOKENS.TRANSITIONS.BUTTON,
      '&:hover': {
        background: 'var(--color-fill-tertiary)',
      },
    },
  }), [baseStyles])
}

export const useNavigationStyles = () => {
  const { theme } = useTheme()
  const baseStyles = useComponentStyles()
  
  return useMemo(() => ({
    ...baseStyles,
    
    navItem: {
      display: 'flex',
      alignItems: 'center',
      padding: `${spacing('SM')}px ${spacing('MD')}px`,
      borderRadius: borderRadius('MD'),
      transition: DESIGN_TOKENS.TRANSITIONS.DEFAULT,
      cursor: 'pointer',
      textDecoration: 'none',
      color: 'var(--color-text-primary)',
      minHeight: DESIGN_TOKENS.TOUCH_TARGET.MIN_SIZE,
      '&:hover': {
        background: 'var(--color-fill-tertiary)',
      },
    },
    
    navItemActive: {
      background: 'rgba(85, 107, 47, 0.1)',
      color: 'var(--color-primary)',
      fontWeight: fontWeight('MEDIUM'),
    },
    
    navIcon: {
      marginRight: spacing('SM'),
      fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_MD,
    },
    
    breadcrumb: {
      display: 'flex',
      alignItems: 'center',
      gap: spacing('XS'),
      fontSize: fontSize('SM'),
      color: 'var(--color-text-secondary)',
    },
    
    breadcrumbSeparator: {
      margin: `0 ${spacing('XS')}px`,
      color: 'var(--color-text-tertiary)',
    },
  }), [theme, baseStyles])
}
