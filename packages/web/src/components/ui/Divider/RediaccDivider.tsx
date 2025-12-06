import { forwardRef } from 'react';
import { StyledRediaccDivider } from './RediaccDivider.styles';
import type { RediaccDividerProps } from './RediaccDivider.types';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
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
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
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
