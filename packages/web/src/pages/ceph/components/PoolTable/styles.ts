import styled from 'styled-components';
import { CloudServerOutlined, DatabaseOutlined } from '@/utils/optimizedIcons';
import { TableContainer as BaseTableContainer, StyledIcon } from '@/styles/primitives';
import { RediaccTag, RediaccCard } from '@/components/ui';
import { ActionsRow, NameCell, NameText, ExpandIcon } from '../../styles/tableAliases';

export const ClusterCard = styled(RediaccCard)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
    box-shadow: ${({ theme }) => theme.shadows.CARD};
    margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  }
`;

export { ActionsRow as CardHeader };

export const CardIcon = styled(StyledIcon).attrs(({ theme }) => ({
  as: CloudServerOutlined,
  $size: 'MD',
  $color: theme.colors.primary,
}))``;

export const CardTitle = styled.span`
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  color: ${({ theme }) => theme.colors.textPrimary};
`;

export const ClusterTag = styled(RediaccTag).attrs({
  variant: 'primary',
  size: 'sm',
})``;

export const TableWrapper = styled(BaseTableContainer)`
  margin-top: ${({ theme }) => theme.spacing.MD}px;
  .pool-row {
    cursor: pointer;
    transition: background-color ${({ theme }) => theme.transitions.FAST};
  }

  .pool-row:hover {
    background: ${({ theme }) => theme.colors.bgHover};
  }
`;

export { NameCell as PoolNameCell, ExpandIcon, NameText as PoolNameText };

export const PoolIcon = styled(StyledIcon).attrs(({ theme }) => ({
  as: DatabaseOutlined,
  $size: 'MD',
  $color: theme.colors.primary,
}))``;
