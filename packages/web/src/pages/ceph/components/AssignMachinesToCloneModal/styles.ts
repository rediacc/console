import styled from 'styled-components';
import { InlineStack } from '@/components/common/styled';
import { RediaccTag } from '@/components/ui';
import {
  BaseModal,
  FlexColumn,
  ModalContentStack,
  ModalTitleRow,
  StyledEmpty,
} from '@/styles/primitives';
import { ModalSize } from '@/types/modal';

export const StyledModal = styled(BaseModal).attrs({
  className: `${ModalSize.Large} assign-clone-machines-modal`,
})``;

export const TitleStack = styled(ModalTitleRow)``;

const TabStack = styled(ModalContentStack)`
  width: 100%;
`;

export const AssignTabContainer = TabStack;
export const ManageTabContainer = TabStack;

export const FieldGroup = styled(FlexColumn).attrs({})``;

export const EmptyState = styled(StyledEmpty)`
`;

export const MachineNameRow = styled(InlineStack)``;

export const BridgeTag = styled(RediaccTag).attrs({
  preset: 'bridge',
  size: 'sm',
  borderless: true,
})`
  && {
    font-size: ${({ theme }) => theme.fontSize.XS}px;
  }
`;
