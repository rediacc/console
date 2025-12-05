import styled from 'styled-components';
import { Typography, Button } from 'antd';
import { BaseModal, ModalBody } from '@/styles/primitives';
import { InlineStack } from '@/components/common/styled';

const { Title, Text } = Typography;

export const StyledModal = styled(BaseModal)`
  .ant-modal-content {
    border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  }
`;

export const TitleStack = InlineStack;

export const DangerTitle = styled(Title).attrs({ level: 4 })`
  && {
    margin: 0;
    color: ${({ theme }) => theme.colors.error};
  }
`;

export const ContentStack = styled(ModalBody)`
  gap: ${({ theme }) => theme.spacing.MD}px;
`;

export const DescriptionText = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`;

export const CountdownCard = styled.div`
  background: ${({ theme }) => theme.colors.bgSecondary};
  padding: ${({ theme }) => `${theme.spacing.SM}px ${theme.spacing.MD}px`};
  border-radius: ${({ theme }) => theme.borderRadius.MD}px;
  text-align: center;
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
`;

export const CountdownText = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.error};
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  }
`;

export const FooterButton = styled(Button)`
  && {
    min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_LG}px;
  }
`;
