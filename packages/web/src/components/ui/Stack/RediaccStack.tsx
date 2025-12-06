import { forwardRef } from 'react';
import { StyledRediaccStack } from './RediaccStack.styles';
import type { RediaccStackProps } from './RediaccStack.types';

export const RediaccStack = forwardRef<HTMLDivElement, RediaccStackProps>(
  (
    {
      direction = 'horizontal',
      gap = 'md',
      align = 'stretch',
      justify = 'start',
      wrap = false,
      fullWidth = false,
      children,
      as,
      ...rest
    },
    ref
  ) => {
    return (
      <StyledRediaccStack
        ref={ref}
        as={as}
        $direction={direction}
        $gap={gap}
        $align={align}
        $justify={justify}
        $wrap={wrap}
        $fullWidth={fullWidth}
        {...rest}
      >
        {children}
      </StyledRediaccStack>
    );
  }
);

RediaccStack.displayName = 'RediaccStack';
