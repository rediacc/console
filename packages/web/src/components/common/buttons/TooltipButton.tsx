import { Button, Tooltip } from 'antd';
import type { ButtonProps } from 'antd';

interface TooltipButtonProps extends ButtonProps {
  /** Tooltip text - also used as aria-label for accessibility */
  tooltip: string;
}

/**
 * Button wrapped with Tooltip and automatic aria-label.
 * Eliminates repeated Tooltip+Button patterns across the codebase.
 *
 * @example
 * <TooltipButton
 *   tooltip={t('actions.create')}
 *   type="primary"
 *   icon={<PlusOutlined />}
 *   onClick={handleCreate}
 * />
 */
export const TooltipButton: React.FC<TooltipButtonProps> = ({ tooltip, ...buttonProps }) => (
  <Tooltip title={tooltip}>
    <Button aria-label={tooltip} {...buttonProps} />
  </Tooltip>
);
