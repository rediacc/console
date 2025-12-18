import { forwardRef } from 'react';
import { resolveStackVariantDefaults, StyledRediaccStack } from './RediaccStack.styles';
import type { RediaccStackProps } from './RediaccStack.types';

export const RediaccStack = forwardRef<HTMLDivElement, RediaccStackProps>(
  (
    {
      variant,
      direction,
      align = 'stretch',
      justify = 'start',
      wrap,
      fullWidth = false,
      children,
      as,
      ...rest
    },
    ref
  ) => {
    // Resolve variant defaults if variant is provided
    const variantDefaults = resolveStackVariantDefaults(variant);

    // Use explicit props if provided, otherwise fall back to variant defaults
    const resolvedDirection = direction ?? variantDefaults.direction;
    const resolvedWrap = wrap ?? variantDefaults.wrap ?? false;

    return (
      <StyledRediaccStack
        ref={ref}
        as={as}
        $direction={resolvedDirection}
        $align={align}
        $justify={justify}
        $wrap={resolvedWrap}
        $fullWidth={fullWidth}
        {...rest}
      >
        {children}
      </StyledRediaccStack>
    );
  }
);

RediaccStack.displayName = 'RediaccStack';
