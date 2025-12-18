/**
 * Danger zone components
 *
 * Components for dangerous actions and warnings:
 * - DangerSection, DangerHeading, DangerStack, DangerDivider
 */

import { Typography } from 'antd';
import styled from 'styled-components';

const { Title } = Typography;

export const DangerSection = styled.section`
  display: flex;
  flex-direction: column;
`;

export const DangerHeading = styled(Title)`
  && {
    color: ${({ theme }) => theme.colors.error};
    display: flex;
    align-items: center;
  }
`;

export const DangerStack = styled.div`
  display: flex;
  flex-direction: column;
  width: 100%;
`;

export const DangerDivider = styled.hr`
`;
