import styled from 'styled-components';
import { RediaccCard } from '@/components/ui';
import { ActionsRow, NameCell, NameText, ExpandIcon } from '@/pages/ceph/styles/tableAliases';
import { TableContainer as BaseTableContainer, StyledIcon } from '@/styles/primitives';
import { CloudServerOutlined, DatabaseOutlined } from '@/utils/optimizedIcons';
import { borderedCard } from '@/styles/mixins';

/**
 * @deprecated Use <RediaccCard spacing="default" /> with inline styles
 * Note: Cannot fully replace due to custom border/shadow - keep wrapper or use inline styles
 */
export const ClusterCard = styled(RediaccCard)`
  && {
    ${borderedCard()}
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

// ClusterTag removed - use <RediaccTag variant="primary" compact> directly

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
