/**
 * Shared form layout configurations.
 * Use spread syntax: <Form {...FORM_LAYOUTS.horizontal}>
 */
export const FORM_LAYOUTS = {
  /**
   * Standard horizontal layout with 8:16 label/wrapper ratio.
   * Use for most forms in modals and panels.
   */
  horizontal: {
    layout: 'horizontal' as const,
    labelCol: { span: 8 },
    wrapperCol: { span: 16 },
  },

  /**
   * Responsive horizontal layout that stacks on mobile.
   * Use for forms that need to work well on small screens.
   */
  responsiveHorizontal: {
    layout: 'horizontal' as const,
    labelCol: { xs: { span: 24 }, sm: { span: 8 } },
    wrapperCol: { xs: { span: 24 }, sm: { span: 16 } },
  },

  /**
   * Vertical layout with labels above inputs.
   * Use for simple forms or narrow containers.
   */
  vertical: {
    layout: 'vertical' as const,
  },
} as const;
