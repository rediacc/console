import { ProLayout } from '@ant-design/pro-components';
import { Flex } from 'antd';
import { styled } from 'goober';

export const MainProLayout = styled(ProLayout)`
  width: 100%;

  .ant-pro-layout-content {
    padding: 1rem;
  }
`;

export const MainLogoButton = styled(Flex)`
  cursor: pointer;
`;

export const MainContent = styled(Flex)`
  width: 100%;
`;

export const TransitionState = styled(Flex)`
  min-height: 240px;
`;
