import { forwardRef } from 'react';
import { StyledRediaccDivider } from './RediaccDivider.styles';
import type { RediaccDividerProps } from './RediaccDivider.types';

export const RediaccDivider = forwardRef<any, RediaccDividerProps>(
  (
    {
      orientation = 'horizontal',
      spacing = 'md',
      dashed = false,
      orientationMargin,
      children,
      ...rest
    },
    ref
  ) => {
    const Component = StyledRediaccDivider as any;
    return (
      <Component
        ref={ref}
        type={orientation}
        $orientation={orientation}
        $spacing={spacing}
        dashed={dashed}
        orientationMargin={orientationMargin}
        {...rest}
      >
        {children}
      </Component>
    );
  }
);

RediaccDivider.displayName = 'RediaccDivider';
