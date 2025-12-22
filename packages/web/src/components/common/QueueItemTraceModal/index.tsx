import React, { lazy, Suspense } from 'react';
import { Flex } from 'antd';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import type { QueueItemTraceModalProps } from './types';

const LazyQueueItemTraceModal = lazy(() => import('./QueueItemTraceModal'));

const QueueItemTraceModal: React.FC<QueueItemTraceModalProps> = (props) => (
  <Suspense
    fallback={
      <LoadingWrapper loading centered minHeight={240}>
        <Flex />
      </LoadingWrapper>
    }
  >
    <LazyQueueItemTraceModal {...props} />
  </Suspense>
);

export type { QueueItemTraceModalProps };
export default QueueItemTraceModal;
