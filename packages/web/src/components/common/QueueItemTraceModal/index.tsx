import React, { lazy, Suspense } from 'react';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import type { QueueItemTraceModalProps } from './types';

const LazyQueueItemTraceModal = lazy(() => import('./QueueItemTraceModal'));

const QueueItemTraceModal: React.FC<QueueItemTraceModalProps> = (props) => (
  <Suspense
    fallback={
      <LoadingWrapper loading centered minHeight={240}>
        <div />
      </LoadingWrapper>
    }
  >
    <LazyQueueItemTraceModal {...props} />
  </Suspense>
);

export type { QueueItemTraceModalProps };
export default QueueItemTraceModal;
