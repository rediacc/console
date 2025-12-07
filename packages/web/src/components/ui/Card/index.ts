import styled from 'styled-components';
import { Card, Typography } from 'antd';

const { Title, Text } = Typography;

export { RediaccCard } from './RediaccCard';
export type { RediaccCardProps, CardVariant, CardSize } from './RediaccCard.types';
export { resolveCardPadding, resolveCardVariantTokens } from './RediaccCard.styles';

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

export const CardHeaderRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: ${({ theme }) => theme.spacing.MD}px;
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
