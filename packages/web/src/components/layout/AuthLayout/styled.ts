import { Flex } from 'antd';
import { styled } from 'goober';

export const AuthLayoutRoot = styled('div')`
  min-height: 100vh;
  width: 100%;
  display: flex;
  flex-direction: column;
  position: relative;
`;

export const AuthLayoutContainer = styled(Flex)`
  flex: 1;
  min-height: 100vh;
`;

export const AuthLayoutBody = styled('div')`
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
`;

export const AuthHeader = styled('div')`
  position: absolute;
  top: 1rem;
  right: 1rem;
  display: flex;
  justify-content: flex-end;
  align-items: center;
`;

export const AuthContent = styled('div')`
  width: 100%;
  max-width: calc(100vw - 2rem);
`;
