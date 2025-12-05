/**
 * Danger zone components
 *
 * Components for dangerous actions and warnings:
 * - DangerSection, DangerHeading, DangerStack, DangerDivider
 */

import styled from 'styled-components';
import { Typography } from 'antd';

const { Title } = Typography;

export const DangerSection = styled.section`
  margin-top: ${({ theme }) => theme.spacing['6']}px;
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.LG}px;
`;

export const DangerHeading = styled(Title)`
  && {
    margin: 0 0 ${({ theme }) => theme.spacing.LG}px;
    color: ${({ theme }) => theme.colors.error};
    display: flex;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.SM}px;
  }
`;

export const DangerStack = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.LG}px;
  width: 100%;
`;

export const DangerDivider = styled.hr`
  border: none;
  border-top: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  margin: 0;
`;
