import type { HookAPI } from 'antd/es/modal/useModal';
import { useTranslation } from 'react-i18next';
import { useCancelQueueItem } from '@/api/api-hooks.generated';
import { confirmAction } from '@/utils/confirmations';

export const useQueueActions = (modal: HookAPI) => {
  const { t } = useTranslation(['queue', 'common']);
  const cancelQueueItemMutation = useCancelQueueItem();

  const handleCancelQueueItem = (taskId: string) => {
    confirmAction({
      modal,
      title: t('queue:cancelConfirm.title'),
      content: t('queue:cancelConfirm.content'),
      okText: t('queue:cancelConfirm.okText'),
      okType: 'danger',
      cancelText: t('common:actions.cancel'),
      onConfirm: async () => {
        await cancelQueueItemMutation.mutateAsync({ taskId });
      },
    });
  };

  return {
    handleCancelQueueItem,
    cancelLoading: cancelQueueItemMutation.isPending,
  };
};
