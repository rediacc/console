import styled from 'styled-components';
import { ActionGroup } from '@/components/common/styled';
import { RediaccProgress, RediaccTag, RediaccText } from '@/components/ui';
import type { TagVariant } from '@/components/ui/Tag';
import { BaseModal, FlexColumn, FlexRow, ModalBody } from '@/styles/primitives';

export const StyledModal = styled(BaseModal)`
  .ant-modal-body {
  }

  .ant-modal-header {
    .ant-modal-title {
      font-size: ${({ theme }) => theme.fontSize.MD}px;

      .anticon {
        font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
      }
    }
  }
`;

export const ModalContent = styled(ModalBody)`
  width: 100%;
`;

export const ProgressSection = styled(FlexColumn).attrs({})``;

export const ProgressBar = styled(RediaccProgress)`
  && {
    .ant-progress-bg {
      background-image: linear-gradient(
        90deg,
        ${({ theme }) => theme.colors.primary} 0%,
        ${({ theme }) => theme.colors.success} 100%
      );
    }
  }
`;

export const SummaryContainer = styled.div`
`;

export const SummaryMetrics = styled(ActionGroup)`
`;

export const SummaryMetric = styled(FlexRow).attrs({
  $align: 'center',
})``;

export const SummaryValue = styled(RediaccText).attrs({ weight: 'semibold' })<{
  $variant?: TagVariant;
}>`
  && {
  }
`;

/** Wrapper for status-based row styling in connectivity test table */
export const StatusTableWrapper = styled.div`
  .status-testing td {
  }

  .status-success td {
  }

  .status-failed td {
  }
`;

export const ResourceTag = styled(RediaccTag).attrs({ variant: 'neutral' })`
  && {
  }
`;

export const StatusPill = styled(RediaccTag)`
  && {
    text-transform: capitalize;
  }
`;

export const MessageText = styled(RediaccText)<{ $isError?: boolean }>`
  && {
  }
`;

export const StyledInfoAlert = styled.div`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
`;
