import type { ReactNode } from 'react';
import { Modal } from 'antd';
import { useTranslation } from 'react-i18next';
import { ExclamationCircleOutlined } from '@ant-design/icons';

interface ConfirmOptions {
  title: string | ReactNode;
  content?: string | ReactNode;
  okText?: string;
  cancelText?: string;
  okType?: 'primary' | 'danger';
  onOk: () => Promise<void> | void;
  onCancel?: () => void;
  testIdPrefix?: string;
  icon?: ReactNode;
}

/**
 * Hook for displaying confirmation dialogs with standardized patterns
 *
 * @example Basic usage
 * ```tsx
 * const { confirm, confirmDelete, contextHolder } = useConfirmDialog();
 *
 * // In your component JSX
 * return (
 *   <>
 *     <Button onClick={() => confirm({
 *       title: 'Are you sure?',
 *       content: 'This action cannot be undone',
 *       onOk: async () => { await deleteItem() }
 *     })}>
 *       Delete
 *     </Button>
 *     {contextHolder}
 *   </>
 * );
 * ```
 *
 * @example Delete confirmation
 * ```tsx
 * const { confirmDelete, contextHolder } = useConfirmDialog();
 *
 * confirmDelete({
 *   title: 'Delete Machine',
 *   content: 'Are you sure you want to delete this machine?',
 *   onOk: async () => { await deleteMachine() },
 *   testIdPrefix: 'machine-delete'
 * });
 * ```
 */
export const useConfirmDialog = () => {
  const { t } = useTranslation(['common']);
  const [modal, contextHolder] = Modal.useModal();

  const confirm = (options: ConfirmOptions) => {
    return modal.confirm({
      title: options.title,
      icon: options.icon !== undefined ? options.icon : <ExclamationCircleOutlined />,
      content: options.content,
      okText: options.okText || t('common:actions.confirm'),
      cancelText: options.cancelText || t('common:actions.cancel'),
      okType: options.okType || 'primary',
      okButtonProps: options.testIdPrefix
        ? { 'data-testid': `${options.testIdPrefix}-confirm-btn` }
        : undefined,
      cancelButtonProps: options.testIdPrefix
        ? { 'data-testid': `${options.testIdPrefix}-cancel-btn` }
        : undefined,
      onOk: options.onOk,
      onCancel: options.onCancel,
    });
  };

  const confirmDelete = (options: Omit<ConfirmOptions, 'okType'>) => {
    return confirm({
      ...options,
      okType: 'danger',
      okText: options.okText || t('common:actions.delete'),
    });
  };

  return {
    confirm,
    confirmDelete,
    contextHolder,
    modal, // Expose raw modal instance for advanced use cases (modal.error, modal.info, etc.)
  };
};
