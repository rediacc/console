import { Flex } from 'antd';
import { styled } from 'goober';

export const ResourceHeaderStack = styled(Flex)``;

export const ResourceHeaderText = styled(Flex)`
  flex: 1;
  min-width: 0;
`;

export const ResourceBody = styled(Flex)`
  flex: 1;
  overflow: hidden;
  position: relative;
`;

export const ResourceBodyContent = styled(Flex)`
  width: 100%;
  height: 100%;
  overflow: auto;
`;
