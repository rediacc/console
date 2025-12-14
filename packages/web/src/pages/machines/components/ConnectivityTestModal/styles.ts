import styled, { keyframes } from 'styled-components';
import { ActionGroup } from '@/components/common/styled';
import { RediaccProgress, RediaccTag, RediaccText } from '@/components/ui';
import type { TagVariant } from '@/components/ui/Tag';
import { BaseModal, FlexColumn, ModalBody } from '@/styles/primitives';

const pulse = keyframes`
  0% {
    opacity: 0.65;
  }
  50% {
    opacity: 1;
  }
  100% {
    opacity: 0.65;
  }
`;

export const StyledModal = styled(BaseModal)`
  .ant-modal-body {
    padding: ${({ theme }) => theme.spacing.XL}px;
  }

  .ant-modal-header {
    .ant-modal-title {
      font-size: ${({ theme }) => theme.fontSize.MD}px;
      color: ${({ theme }) => theme.colors.textPrimary};

      .anticon {
        font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
      }
    }
  }
`;

export const ModalContent = styled(ModalBody)`
  width: 100%;
`;

export const ProgressSection = styled(FlexColumn).attrs({
  $gap: 'XS',
})``;

export const ProgressBar = styled(RediaccProgress)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;

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
  padding: ${({ theme }) => theme.spacing.MD}px;
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  background-color: ${({ theme }) => theme.colors.bgSecondary};
`;

export const SummaryMetrics = styled(ActionGroup)`
  gap: ${({ theme }) => theme.spacing.XL}px;
`;

export const SummaryMetric = styled(FlexColumn).attrs({
  $gap: 'XS',
})``;

export const SummaryValue = styled(RediaccText).attrs({ weight: 'semibold' })<{
  $variant?: TagVariant;
}>`
  && {
    color: ${({ theme, $variant }) =>
      $variant === 'success'
        ? theme.colors.success
        : $variant === 'error'
          ? theme.colors.error
          : theme.colors.textPrimary};
  }
`;

/** Wrapper for status-based row styling in connectivity test table */
export const StatusTableWrapper = styled.div`
  .status-testing td {
    animation: ${pulse} ${({ theme }) => theme.transitions.SLOW};
    background-color: ${({ theme }) => theme.colors.primaryBg};
  }

  .status-success td {
    background-color: ${({ theme }) => theme.colors.bgSuccess};
  }

  .status-failed td {
    background-color: ${({ theme }) => theme.colors.bgError};
  }
`;

export const ResourceTag = styled(RediaccTag).attrs({ variant: 'neutral' })`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
  }
`;

export const StatusPill = styled(RediaccTag)`
  && {
    text-transform: capitalize;
  }
`;

export const MessageText = styled(RediaccText)<{ $isError?: boolean }>`
  && {
    color: ${({ theme, $isError }) => ($isError ? theme.colors.error : theme.colors.textPrimary)};
  }
`;

export const StyledInfoAlert = styled.div`
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  font-size: ${({ theme }) => theme.fontSize.SM}px;
`;
