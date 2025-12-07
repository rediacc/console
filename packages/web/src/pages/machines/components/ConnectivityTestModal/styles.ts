import styled, { keyframes } from 'styled-components';
import { ActionGroup } from '@/components/common/styled';
import {
  RediaccTag,
  RediaccText,
  RediaccAlert,
  RediaccStack,
  RediaccProgress,
} from '@/components/ui';
import type { TagVariant } from '@/components/ui/Tag';
import { BaseModal, BaseTable, ModalBody, FlexColumn } from '@/styles/primitives';

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
`;

export const ModalContent = styled(ModalBody)`
  width: 100%;
`;

export const TitleStack = styled(RediaccStack).attrs({ direction: 'horizontal' })`
  && {
    display: inline-flex;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.SM}px;
    font-size: ${({ theme }) => theme.fontSize.BASE}px;
    color: ${({ theme }) => theme.colors.textPrimary};

    .anticon {
      font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
    }
  }
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

export const ProgressNote = styled(RediaccText).attrs({ size: 'xs', color: 'secondary' })``;

export const InfoAlert = styled(RediaccAlert)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
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

export const SummaryLabel = styled(RediaccText).attrs({ color: 'secondary' })``;

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

export const StyledTable = styled(BaseTable)`
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

export const MachineName = styled(RediaccText).attrs({ weight: 'semibold' })``;

export const StatusIcon = styled.span<{ $variant: 'testing' | 'success' | 'failed' | 'pending' }>`
  display: inline-flex;
  align-items: center;
  color: ${({ theme, $variant }) => {
    switch ($variant) {
      case 'success':
        return theme.colors.success;
      case 'failed':
        return theme.colors.error;
      case 'testing':
        return theme.colors.primary;
      case 'pending':
      default:
        return theme.colors.textSecondary;
    }
  }};

  .anticon {
    font-size: ${({ theme }) => theme.fontSize.LG}px;
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
