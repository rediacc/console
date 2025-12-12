import type { StatisticProps } from 'antd';

export type StatisticVariant =
  | 'default'
  | 'primary'
  | 'warning'
  | 'error'
  | 'success'
  | 'info'
  | 'textPrimary';

export interface RediaccStatisticProps extends Omit<StatisticProps, 'valueStyle'> {
  /** Color variant for the statistic value */
  variant?: StatisticVariant;
  /** Override to error color when critical condition is met */
  critical?: boolean;
  /** Direct color override (takes precedence over variant) */
  color?: string;
}
