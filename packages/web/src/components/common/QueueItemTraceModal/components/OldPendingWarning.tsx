import React from 'react';
import { RediaccAlert } from '@/components/ui';
import { WarningOutlined } from '@/utils/optimizedIcons';
import { isStalePending } from '../utils';

interface OldPendingWarningProps {
  queueDetails: Record<string, unknown> | null | undefined;
}

export const OldPendingWarning: React.FC<OldPendingWarningProps> = ({ queueDetails }) => {
  if (!queueDetails || !isStalePending(queueDetails)) {
    return null;
  }

  return (
    <RediaccAlert
      data-testid="queue-trace-alert-old-pending"
      message="Old Pending Task"
      description="This task has been pending for over 6 hours. It may expire soon if not processed."
      variant="warning"
      showIcon
      icon={<WarningOutlined />}
    />
  );
};
