import styled from 'styled-components';
import { BaseModal, ModalBody } from '@/styles/primitives';
import { InlineStack } from '@/components/common/styled';
import { RediaccText } from '@/components/ui/Text';
import { RediaccButton } from '@/components/ui/Button';

export const StyledModal = styled(BaseModal)`
  .ant-modal-content {
    border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  }
`;

export const TitleStack = InlineStack;

export const DangerTitle = styled(RediaccText).attrs({ size: 'xl', weight: 'semibold' })`
  && {
    margin: 0;
    color: ${({ theme }) => theme.colors.error};
  }
`;

export const ContentStack = styled(ModalBody)`
  gap: ${({ theme }) => theme.spacing.MD}px;
`;

export const DescriptionText = styled(RediaccText).attrs({ color: 'secondary' })``;;

export const CountdownCard = styled.div`
  background: ${({ theme }) => theme.colors.bgSecondary};
  padding: ${({ theme }) => `${theme.spacing.SM}px ${theme.spacing.MD}px`};
  border-radius: ${({ theme }) => theme.borderRadius.MD}px;
  text-align: center;
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
`;

export const CountdownText = styled(RediaccText).attrs({ weight: 'semibold' })`
  && {
    color: ${({ theme }) => theme.colors.error};
  }
`;

export const FooterButton = styled(RediaccButton)`
  && {
    min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_LG}px;
  }
`;
