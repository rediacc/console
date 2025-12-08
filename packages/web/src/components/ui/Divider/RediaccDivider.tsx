import { StyledRediaccDivider } from './RediaccDivider.styles';
import type { RediaccDividerProps } from './RediaccDivider.types';

export const RediaccDivider: React.FC<RediaccDividerProps> = ({
  orientation = 'horizontal',
  spacing = 'md',
  dashed = false,
  orientationMargin,
  children,
  ...rest
}) => {
  return (
    <StyledRediaccDivider
      type={orientation}
      $orientation={orientation}
      $spacing={spacing}
      dashed={dashed}
      orientationMargin={orientationMargin}
      {...rest}
    >
      {children}
    </StyledRediaccDivider>
  );
};

RediaccDivider.displayName = 'RediaccDivider';
