import styled, { keyframes } from 'styled-components';
import { Typography, Progress, Alert, Space, Tag, Button } from 'antd';
import {
  BaseModal,
  BaseTable,
  ModalBody,
  ModalContentStack,
  ModalFooterActions as PrimitiveModalFooterActions,
  PrimaryButton as PrimitivePrimaryButton,
  StatusTag,
  StatusVariant,
} from '@/styles/primitives';

const { Text } = Typography;

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

export const ContentStack = styled(ModalContentStack)``;

export const TitleStack = styled(Space)`
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

export const ModalFooterActions = styled(PrimitiveModalFooterActions)``;

export const PrimaryActionButton = styled(PrimitivePrimaryButton)`
  && {
    min-width: ${({ theme }) => theme.spacing.XXL * 2}px;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;

export const SecondaryIconButton = styled(Button)`
  && {
    min-width: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
    min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;

export const ProgressSection = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.XS}px;
`;

export const ProgressBar = styled(Progress)`
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

export const ProgressNote = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`;

export const InfoAlert = styled(Alert)`
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

export const SummaryMetrics = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.XL}px;
`;

export const SummaryMetric = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.XS}px;
`;

export const SummaryLabel = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`;

export const SummaryValue = styled(Text)<{ $variant?: StatusVariant }>`
  && {
    color: ${({ theme, $variant }) =>
      $variant === 'success'
        ? theme.colors.success
        : $variant === 'error'
          ? theme.colors.error
          : theme.colors.textPrimary};
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
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

export const MachineCell = styled.div`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const MachineName = styled(Text)`
  && {
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  }
`;

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

export const ResourceTag = styled(Tag)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    border-color: ${({ theme }) => theme.colors.borderSecondary};
    color: ${({ theme }) => theme.colors.textPrimary};
    background-color: ${({ theme }) => theme.colors.bgSecondary};
  }
`;

export const StatusPill = styled(StatusTag)`
  && {
    text-transform: capitalize;
  }
`;

export const MessageText = styled(Text)<{ $isError?: boolean }>`
  && {
    color: ${({ theme, $isError }) => ($isError ? theme.colors.error : theme.colors.textPrimary)};
  }
`;
