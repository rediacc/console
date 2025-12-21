import { Alert } from 'antd';
import React from 'react';
import { WarningOutlined } from '@/utils/optimizedIcons';
import type { GetTeamQueueItems_ResultSet1 } from '@rediacc/shared/types';
import { isStalePending } from '../utils';

interface OldPendingWarningProps {
  queueDetails: GetTeamQueueItems_ResultSet1 | null | undefined;
}

export const OldPendingWarning: React.FC<OldPendingWarningProps> = ({ queueDetails }) => {
  if (!queueDetails || !isStalePending(queueDetails)) {
    return null;
  }

  return (
    <Alert
      data-testid="queue-trace-alert-old-pending"
      message="Old Pending Task"
      description="This task has been pending for over 6 hours. It may expire soon if not processed."
      type="warning"
      showIcon
      icon={<WarningOutlined />}
    />
  );
};
