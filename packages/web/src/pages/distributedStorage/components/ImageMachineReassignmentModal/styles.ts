import styled from 'styled-components';
import { Typography } from 'antd';
import {
  BaseModal,
  HelperText as PrimitiveHelperText,
  FormLabel,
  StyledIcon,
  AlertCard,
} from '@/styles/primitives';
import { ModalSelect, ContentStack, InlineStack } from '@/components/common/styled';
import { ModalSize } from '@/types/modal';
import { CloudServerOutlined, FileImageOutlined } from '@/utils/optimizedIcons';

const { Text } = Typography;

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

export const FieldLabel = styled(FormLabel)`
  && {
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  }
`;

export const FieldValue = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`;

export const InfoAlert = styled(AlertCard).attrs({ $variant: 'info' })``;
export const WarningAlert = styled(AlertCard).attrs({ $variant: 'warning' })``;

export const MachineIcon = styled(StyledIcon).attrs(({ theme }) => ({
  as: CloudServerOutlined,
  $size: theme.fontSize.BASE,
  $color: theme.colors.primary,
}))``;

export const StyledSelect = ModalSelect;

export const SelectLabel = styled(FormLabel)`
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

export const HelperText = PrimitiveHelperText;

export const LoadingContainer = styled.div`
  display: flex;
  justify-content: center;
  padding: ${({ theme }) => theme.spacing.MD}px 0;
`;
