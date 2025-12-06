import { forwardRef } from 'react';
import { StyledRediaccDivider } from './RediaccDivider.styles';
import type { RediaccDividerProps } from './RediaccDivider.types';

export const RediaccDivider = forwardRef<HTMLElement, RediaccDividerProps>(
  (
    {
      orientation = 'horizontal',
      spacing = 'md',
      dashed = false,
      children,
      ...rest
    },
    ref
  ) => {
    return (
      <StyledRediaccDivider
        ref={ref}
        type={orientation}
        $orientation={orientation}
        $spacing={spacing}
        dashed={dashed}
        {...rest}
      >
        {children}
      </StyledRediaccDivider>
    );
  }
);

RediaccDivider.displayName = 'RediaccDivider';
