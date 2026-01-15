import type { ButtonProps, PopconfirmProps } from 'antd';
import { Button, Popconfirm, Tooltip } from 'antd';

interface ConfirmButtonProps extends Omit<ButtonProps, 'onClick'> {
  /** Tooltip text - also used as aria-label for accessibility */
  tooltip: string;
  /** Popconfirm title (main question) */
  confirmTitle: string;
  /** Popconfirm description (additional context) */
  confirmDescription?: string;
  /** Handler called when user confirms */
  onConfirm: () => void;
  /** Confirm button text (defaults to tooltip) */
  confirmText?: string;
  /** Cancel button text */
  cancelText?: string;
  /** Additional Popconfirm props */
  popconfirmProps?: Omit<
    PopconfirmProps,
    'title' | 'description' | 'onConfirm' | 'okText' | 'cancelText' | 'okButtonProps'
  >;
}

/**
 * Button with Popconfirm and Tooltip for dangerous/confirmation-required actions.
 * Eliminates repeated Popconfirm+Tooltip+Button nesting patterns.
 *
 * @example
 * <ConfirmButton
 *   tooltip={t('actions.delete')}
 *   confirmTitle={t('confirm.deleteTitle')}
 *   confirmDescription={t('confirm.deleteWarning')}
 *   onConfirm={() => handleDelete(item)}
 *   danger
 *   icon={<DeleteOutlined />}
 * />
 */
export const ConfirmButton: React.FC<ConfirmButtonProps> = ({
  tooltip,
  confirmTitle,
  confirmDescription,
  onConfirm,
  confirmText,
  cancelText,
  popconfirmProps,
  danger,
  ...buttonProps
}) => (
  <Popconfirm
    title={confirmTitle}
    description={confirmDescription}
    onConfirm={onConfirm}
    okText={confirmText ?? tooltip}
    cancelText={cancelText}
    okButtonProps={{ danger }}
    {...popconfirmProps}
  >
    <Tooltip title={tooltip}>
      <Button aria-label={tooltip} danger={danger} {...buttonProps} />
    </Tooltip>
  </Popconfirm>
);
