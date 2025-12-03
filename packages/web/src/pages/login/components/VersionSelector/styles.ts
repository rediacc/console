import styled from 'styled-components';
import { Typography } from 'antd';

const { Text: AntText } = Typography;

export const VersionText = styled(AntText)`
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  opacity: 0.6;
`;
