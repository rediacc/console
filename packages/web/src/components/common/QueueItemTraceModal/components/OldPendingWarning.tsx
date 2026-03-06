import type { GetTeamQueueItems_ResultSet1 } from '@rediacc/shared/types';
import { Alert } from 'antd';
import React from 'react';
import { useTranslation } from 'react-i18next';
import { WarningOutlined } from '@/utils/optimizedIcons';
import { isStalePending } from '../utils';

interface OldPendingWarningProps {
  queueDetails: GetTeamQueueItems_ResultSet1 | null | undefined;
}

export const OldPendingWarning: React.FC<OldPendingWarningProps> = ({ queueDetails }) => {
  const { t } = useTranslation('queue');

  if (!queueDetails || !isStalePending(queueDetails)) {
    return null;
  }

  return (
    <Alert
      data-testid="queue-trace-alert-old-pending"
      message={t('trace.oldPendingTitle')}
      description={t('trace.oldPendingDescription')}
      type="warning"
      icon={<WarningOutlined />}
    />
  );
};
