import styled from 'styled-components';
import { Layout } from 'antd';

const { Content } = Layout;

export const AuthLayoutContainer = styled(Layout)`
  min-height: 100vh;
  background: ${({ theme }) => theme.colors.bgSecondary};
`;

export const ControlsWrapper = styled.div`
  position: absolute;
  top: ${({ theme }) => theme.spacing.PAGE_CONTAINER}px;
  right: ${({ theme }) => theme.spacing.PAGE_CONTAINER}px;
  z-index: ${({ theme }) => theme.zIndex.DROPDOWN};
`;

export const AuthContent = styled(Content)`
  display: flex;
  align-items: center;
  justify-content: center;
  padding: ${({ theme }) => theme.spacing.PAGE_CONTAINER}px;
`;
