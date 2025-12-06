/**
 * Card components
 *
 * Building blocks for card-based layouts:
 * - PageCard: Main card wrapper for page content
 * - CardContent, CardHeader, CardTitle, CardDescription, CardActions
 * - CardHeaderRow for legacy compatibility
 */

import styled from 'styled-components';
import { Typography, Card } from 'antd';
import { SectionHeaderRow as PrimitiveHeaderRow } from '@/styles/primitives';

const { Title, Text } = Typography;

export const PageCard = styled(Card).attrs({ className: 'page-card' })``;

export const CardContent = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.MD}px;
  width: 100%;
`;

export const CardHeader = styled.div`
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const CardHeaderRow = styled(PrimitiveHeaderRow)`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`;

export const CardTitle = styled(Title)`
  && {
    margin: 0;
  }
`;

export const CardDescription = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`;

export const CardActions = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
  margin-top: ${({ theme }) => theme.spacing.MD}px;
`;
