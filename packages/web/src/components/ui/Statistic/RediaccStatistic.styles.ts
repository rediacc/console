import { Statistic } from 'antd';
import styled from 'styled-components';
import type { StyledTheme } from '@/styles/styledTheme';
import type { StatisticVariant } from './RediaccStatistic.types';

/** Maps statistic variant to theme color key */
const VARIANT_COLOR_MAP: Record<StatisticVariant, keyof StyledTheme['colors']> = {
  default: 'textPrimary',
  primary: 'primary',
  warning: 'warning',
  error: 'error',
  success: 'success',
  info: 'info',
  textPrimary: 'textPrimary',
};

/** Get statistic value color based on variant */
export const resolveStatisticColor = (
  variant: StatisticVariant = 'default',
  theme: StyledTheme
): string => theme.colors[VARIANT_COLOR_MAP[variant]];

export const StyledRediaccStatistic = styled(Statistic)<{
  $variant: StatisticVariant;
  $critical: boolean;
  $color?: string;
}>`
  .ant-statistic-content-value {
    color: ${({ theme, $variant, $critical, $color }) =>
      $color ? $color : $critical ? theme.colors.error : resolveStatisticColor($variant, theme)};
  }
`;
