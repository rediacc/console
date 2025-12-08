import { useTranslation } from 'react-i18next';
import { useCancelQueueItem } from '@/api/queries/queue';
import { confirmAction } from '@/utils/confirmations';
import type { HookAPI } from 'antd/es/modal/useModal';

export const useQueueActions = (modal: HookAPI) => {
  const { t } = useTranslation(['queue', 'common']);
  const cancelQueueItemMutation = useCancelQueueItem();

  const handleCancelQueueItem = async (taskId: string) => {
    confirmAction({
      modal,
      title: t('queue:cancelConfirm.title') as string,
      content: t('queue:cancelConfirm.content') as string,
      okText: t('queue:cancelConfirm.okText') as string,
      okType: 'danger',
      cancelText: t('common:actions.cancel') as string,
      onConfirm: async () => {
        await cancelQueueItemMutation.mutateAsync(taskId);
      },
    });
  };

  return {
    handleCancelQueueItem,
    cancelLoading: cancelQueueItemMutation.isPending,
  };
};
