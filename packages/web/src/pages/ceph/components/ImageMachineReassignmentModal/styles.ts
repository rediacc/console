import styled from 'styled-components';
import { ContentStack, InlineStack } from '@/components/common/styled';
import { RediaccSelect } from '@/components/ui';
import { BaseModal, LoadingContainer, StyledIcon } from '@/styles/primitives';
import { ModalSize } from '@/types/modal';
import { CloudServerOutlined, FileImageOutlined } from '@/utils/optimizedIcons';

export { ContentStack, LoadingContainer };

export const StyledModal = styled(BaseModal).attrs({
  className: `${ModalSize.Medium} image-machine-reassignment-modal`,
})`
  .ant-modal-body {
    display: flex;
    flex-direction: column;
  }

  .ant-modal-footer {
    display: flex;
    justify-content: flex-end;
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
`;

export const MachineIcon = styled(StyledIcon).attrs(({ theme }) => ({
  as: CloudServerOutlined,
  $size: theme.fontSize.MD,
  $color: theme.colors.primary,
}))``;

export const StyledSelect = RediaccSelect;

export const SelectOptionText = styled.span`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
`;

export const DisabledOptionText = styled(SelectOptionText)`
  cursor: not-allowed;
`;
