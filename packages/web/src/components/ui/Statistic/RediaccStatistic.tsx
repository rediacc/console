import { StyledRediaccStatistic } from './RediaccStatistic.styles';
import type { RediaccStatisticProps } from './RediaccStatistic.types';

export const RediaccStatistic: React.FC<RediaccStatisticProps> = ({
  variant = 'default',
  critical = false,
  color,
  ...rest
}) => {
  return (
    <StyledRediaccStatistic $variant={variant} $critical={critical} $color={color} {...rest} />
  );
};
