import { Card, Typography } from 'antd';
import styled from 'styled-components';

const { Title, Text } = Typography;

export { RediaccCard } from './RediaccCard';
export { resolveCardPadding, resolveCardVariantTokens } from './RediaccCard.styles';
export type { CardSize, CardVariant, RediaccCardProps } from './RediaccCard.types';

export const PageCard = styled(Card).attrs({ className: 'page-card' })``;

export const CardContent = styled.div`
  display: flex;
  flex-direction: column;
  width: 100%;
`;

export const CardHeader = styled.div`
  display: flex;
  align-items: center;
  flex-wrap: wrap;
`;

export const CardHeaderRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
`;

export const CardTitle = styled(Title)`
  && {
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
`;
