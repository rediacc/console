import styled from 'styled-components';
import {
  BaseModal,
  StyledIcon,
  AlertCard,
} from '@/styles/primitives';
import { ContentStack, InlineStack } from '@/components/common/styled';
import { RediaccSelect as UISelect, RediaccText as Text } from '@/components/ui';
import { ModalSize } from '@/types/modal';
import { CloudServerOutlined, FileImageOutlined } from '@/utils/optimizedIcons';

export { ContentStack };

export const StyledModal = styled(BaseModal).attrs({
  className: `${ModalSize.Medium} image-machine-reassignment-modal`,
})`
  .ant-modal-body {
    display: flex;
    flex-direction: column;
    gap: ${({ theme }) => theme.spacing.LG}px;
  }

  .ant-modal-footer {
    display: flex;
    justify-content: flex-end;
    gap: ${({ theme }) => theme.spacing.SM}px;
  }
`;

export const TitleStack = InlineStack;

export const TitleIcon = styled(StyledIcon).attrs(({ theme }) => ({
  as: FileImageOutlined,
  $size: theme.fontSize.LG,
  $color: theme.colors.primary,
}))``;

export const FieldRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.XS}px;
`;

export const FieldLabel = styled(Text).attrs({
  weight: 'semibold',
  size: 'sm',
})``;

export const FieldValue = styled(Text).attrs({
  color: 'muted',
})``;

export const InfoAlert = styled(AlertCard).attrs({ $variant: 'info' })``;
export const WarningAlert = styled(AlertCard).attrs({ $variant: 'warning' })``;

export const MachineIcon = styled(StyledIcon).attrs(({ theme }) => ({
  as: CloudServerOutlined,
  $size: theme.fontSize.BASE,
  $color: theme.colors.primary,
}))``;

export const StyledSelect = UISelect;

export const SelectLabel = styled(Text).attrs({
  weight: 'medium',
  size: 'sm',
})`
  && {
    display: block;
    margin-bottom: ${({ theme }) => theme.spacing.XS}px;
  }
`;

export const SelectOptionText = styled.span`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  color: ${({ theme }) => theme.colors.textPrimary};
`;

export const DisabledOptionText = styled(SelectOptionText)`
  opacity: 0.6;
`;

export const HelperText = styled(Text).attrs({
  variant: 'caption',
})``;

export const LoadingContainer = styled.div`
  display: flex;
  justify-content: center;
  padding: ${({ theme }) => theme.spacing.MD}px 0;
`;
