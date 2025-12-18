import { useMemo } from 'react';
import { useTheme } from '@/context/ThemeContext';
import {
  borderRadius,
  createButtonStyle,
  createCardStyle,
  createControlSurfaceStyle,
  createInputStyle,
  createModalStyle,
  createTypographyStyle,
  DESIGN_TOKENS,
  fontSize,
  fontWeight,
  spacing,
} from '@/utils/styleConstants';

export const useComponentStyles = () => {
  const { theme } = useTheme();

  return useMemo(
    () => ({
      // Control surfaces
      controlSurface: createControlSurfaceStyle(),
      controlSurfaceLarge: createControlSurfaceStyle(DESIGN_TOKENS.DIMENSIONS.FORM_CONTROL_HEIGHT),
      controlSurfaceSmall: createControlSurfaceStyle(DESIGN_TOKENS.DIMENSIONS.FORM_CONTROL_HEIGHT),

      // Cards and modals
      card: createCardStyle(),
      cardLarge: createCardStyle(DESIGN_TOKENS.DIMENSIONS.CARD_WIDTH_LG),
      modal: createModalStyle(),
      modalLarge: createModalStyle(DESIGN_TOKENS.DIMENSIONS.MODAL_WIDTH_LG),
      modalXLarge: createModalStyle(DESIGN_TOKENS.DIMENSIONS.MODAL_WIDTH_XL),

      // Form elements
      input: createInputStyle(),
      inputSmall: createInputStyle(DESIGN_TOKENS.DIMENSIONS.FORM_CONTROL_HEIGHT),
      inputLarge: createInputStyle(DESIGN_TOKENS.DIMENSIONS.FORM_CONTROL_HEIGHT),

      // Buttons
      buttonPrimary: createButtonStyle('primary'),
      buttonSecondary: createButtonStyle('secondary'),
      buttonGhost: createButtonStyle('ghost'),

      // Typography (matching style-guide.md)
      heading1: createTypographyStyle('XXXXL', 'SEMIBOLD', 'TIGHT'),
      heading2: createTypographyStyle('XXXL', 'SEMIBOLD', 'TIGHT'),
      heading3: createTypographyStyle('XXL', 'SEMIBOLD', 'NORMAL'),
      heading4: createTypographyStyle('XL', 'SEMIBOLD', 'NORMAL'),
      heading5: createTypographyStyle('LG', 'MEDIUM', 'NORMAL'),
      heading6: createTypographyStyle('MD', 'MEDIUM', 'NORMAL'),
      bodyLarge: createTypographyStyle('LG', 'REGULAR', 'RELAXED'),
      body: createTypographyStyle('MD', 'REGULAR', 'NORMAL'),
      bodySmall: createTypographyStyle('SM', 'REGULAR', 'NORMAL'),
      caption: createTypographyStyle('XS', 'REGULAR', 'NORMAL'),
      label: createTypographyStyle('SM', 'MEDIUM', 'NORMAL'),

      // Layout
      container: {
        padding: spacing('PAGE_CONTAINER'),
        maxWidth: '100%',
      },
      section: {},
      spacer: {},

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
        background: 'var(--color-bg-primary)',
      },
      header: {
        height: DESIGN_TOKENS.DIMENSIONS.HEADER_HEIGHT,
        background: 'var(--color-bg-primary)',
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
      errorField: {},
      errorMessage: {
        ...createTypographyStyle('XS', 'REGULAR', 'NORMAL'),
        color: 'var(--color-error)',
      },

      // Loading states
      // Note: Opacity removed - use Skeleton components instead
      loading: {
        pointerEvents: 'none' as const,
      },

      // Hover effects
      hoverEffect: {
        '&:hover': {},
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
        overflow: 'hidden',
        clip: 'rect(0, 0, 0, 0)',
        whiteSpace: 'nowrap' as const,
      },
    }),
    [theme]
  );
};

// Specialized hooks for specific component types
export const useFormStyles = () => {
  const baseStyles = useComponentStyles();

  return useMemo(
    () => ({
      ...baseStyles,

      formGroup: {},

      formLabel: {
        ...createTypographyStyle('SM', 'MEDIUM', 'NORMAL'),
        color: 'var(--color-text-primary)',
        display: 'block',
      },

      formInput: {
        ...baseStyles.input,
        '&:focus': {
          ...baseStyles.focusVisible,
        },
      },

      formError: {
        ...baseStyles.errorMessage,
        display: 'flex',
        alignItems: 'center',
      },

      formHelper: {
        ...createTypographyStyle('XS', 'REGULAR', 'NORMAL'),
        color: 'var(--color-text-secondary)',
      },

      fieldset: {
        borderRadius: borderRadius('LG'),
        padding: spacing('MD'),
      },

      legend: {
        ...createTypographyStyle('SM', 'MEDIUM', 'NORMAL'),
        color: 'var(--color-text-primary)',
        padding: `0 ${spacing('SM')}px`,
      },
    }),
    [baseStyles]
  );
};

export const useTableStyles = () => {
  const baseStyles = useComponentStyles();

  return useMemo(
    () => ({
      ...baseStyles,

      tableContainer: {
        overflow: 'hidden',
        borderRadius: borderRadius('LG'),
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
        ...createControlSurfaceStyle(DESIGN_TOKENS.DIMENSIONS.FORM_CONTROL_HEIGHT),
        borderRadius: borderRadius('MD'),
        background: 'transparent',
        cursor: 'pointer',
        '&:hover': {
          background: 'var(--color-fill-tertiary)',
        },
      },

      // Row state styles for custom row classNames
      tableRowInteractive: {
        cursor: 'pointer',
      },

      tableRowHover: {
        backgroundColor: 'var(--color-bg-primary)',
      },

      tableRowSelected: {
        backgroundColor: 'var(--color-primary-bg)',
      },

      tableRowHighlighted: {
        backgroundColor: 'var(--color-primary-bg)',
      },

      // Loading overlay styles
      // Note: Opacity removed - use solid background
      tableLoadingOverlay: {
        position: 'absolute' as const,
        inset: 0,
        backgroundColor: 'var(--color-bg-primary)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: DESIGN_TOKENS.Z_INDEX.OVERLAY,
        borderRadius: borderRadius('SM'),
      },
    }),
    [baseStyles]
  );
};

export const useNavigationStyles = () => {
  const baseStyles = useComponentStyles();

  return useMemo(
    () => ({
      ...baseStyles,

      navItem: {
        display: 'flex',
        alignItems: 'center',
        padding: `${spacing('SM')}px ${spacing('MD')}px`,
        borderRadius: borderRadius('MD'),
        cursor: 'pointer',
        textDecoration: 'none',
        color: 'var(--color-text-primary)',
        minHeight: DESIGN_TOKENS.DIMENSIONS.FORM_CONTROL_HEIGHT,
        '&:hover': {
          background: 'var(--color-fill-tertiary)',
        },
      },

      navItemActive: {
        background: 'var(--overlay-nav-active)',
        color: 'var(--color-primary)',
        fontWeight: fontWeight('MEDIUM'),
      },

      navIcon: {
        fontSize: DESIGN_TOKENS.DIMENSIONS.ICON_MD,
      },

      breadcrumb: {
        display: 'flex',
        alignItems: 'center',
        fontSize: fontSize('SM'),
        color: 'var(--color-text-secondary)',
      },

      breadcrumbSeparator: {
        color: 'var(--color-text-tertiary)',
      },
    }),
    [baseStyles]
  );
};
