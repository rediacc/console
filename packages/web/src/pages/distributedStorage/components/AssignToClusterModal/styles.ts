import styled from 'styled-components';
import { Typography } from 'antd';
import {
  BaseModal,
  BaseTable,
  FlexColumn,
  FlexRow,
  ModalContentStack,
  ModalTitleRow,
  PillTag,
  HelperText as PrimitiveHelperText,
  FormLabel,
  AlertCard,
} from '@/styles/primitives';
import { InlineStack, ModalSelect } from '@/components/common/styled';
import { ModalSize } from '@/types/modal';

const { Text } = Typography;

export const StyledModal = styled(BaseModal).attrs<{ $size: ModalSize }>(({ $size }) => ({
  className: `${$size} assign-to-cluster-modal`,
}))<{ $size: ModalSize }>``;

export const TitleStack = styled(ModalTitleRow)``;

export const ContentStack = styled(ModalContentStack)`
  width: 100%;
`;

export const InfoAlert = styled(AlertCard).attrs({ $variant: 'info' })``;

export const ClusterAlert = styled(AlertCard).attrs({ $variant: 'warning' })`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`;

export const MachineDetailsSection = styled(FlexColumn).attrs({ $gap: 'SM' })``;

export const DetailRow = styled(InlineStack).attrs({ $align: 'flex-start' })`
  gap: ${({ theme }) => theme.spacing.XS}px;
`;

export const DetailLabel = styled(Text)`
  && {
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`;

export const DetailValue = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`;

export const FieldGroup = styled(FlexColumn).attrs({ $gap: 'XS' })``;

export const FieldLabel = FormLabel;

export const StyledSelect = ModalSelect;

export const HelperText = PrimitiveHelperText;

export const LoadingWrapper = styled(FlexRow).attrs({ $gap: 'SM' })``;

export const MachinesTable = styled(BaseTable)`
  .ant-table-tbody > tr > td {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;

export const MachineNameRow = styled(InlineStack)``;

export const MachineNameText = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textPrimary};
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  }
`;

export const TeamTag = styled(PillTag).attrs({
  $variant: 'success',
  $size: 'SM',
  $borderless: true,
})`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
  }
`;

export const AssignmentTag = styled(PillTag).attrs({
  $size: 'SM',
})<{ $variant: 'cluster' | 'available' }>`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
    padding: 0 ${({ theme }) => theme.spacing.XS}px;
  }
`;
