import React, { lazy, Suspense } from 'react';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import type { AuditTraceModalProps } from './AuditTraceModal';

const LazyAuditTraceModal = lazy(() => import('./AuditTraceModal'));

const AuditTraceModal: React.FC<AuditTraceModalProps> = (props) => (
  <Suspense
    fallback={
      <LoadingWrapper loading centered minHeight={200}>
        <div />
      </LoadingWrapper>
    }
  >
    <LazyAuditTraceModal {...props} />
  </Suspense>
);

export type { AuditTraceModalProps };
export default AuditTraceModal;
