import { Statistic } from 'antd';
import styled from 'styled-components';
import type { StyledTheme } from '@/styles/styledTheme';
import type { StatisticVariant } from './RediaccStatistic.types';

// Get statistic value color based on variant
export const resolveStatisticColor = (
  variant: StatisticVariant = 'default',
  theme: StyledTheme
): string => {
  switch (variant) {
    case 'primary':
      return theme.colors.primary;
    case 'success':
      return theme.colors.success;
    case 'warning':
      return theme.colors.warning;
    case 'error':
      return theme.colors.error;
    case 'info':
      return theme.colors.info;
    case 'textPrimary':
      return theme.colors.textPrimary;
    case 'default':
    default:
      return theme.colors.textPrimary;
  }
};

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
