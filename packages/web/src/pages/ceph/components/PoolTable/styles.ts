import styled from 'styled-components';
import { RediaccCard } from '@/components/ui';
import { TableWrapper as UITableWrapper } from '@/components/ui/Table';
import { ActionsRow, ExpandIcon, NameCell, NameText } from '@/pages/ceph/styles/tableAliases';
import { borderedCard } from '@/styles/mixins';
import { StyledIcon } from '@/styles/primitives';
import { CloudServerOutlined, DatabaseOutlined } from '@/utils/optimizedIcons';

/** Card wrapper for cluster pool groupings with bordered styling */
export const ClusterCard = styled(RediaccCard)`
  && {
    ${borderedCard()}
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
`;

// ClusterTag removed - use <RediaccTag variant="primary" compact> directly

export const TableWrapper = styled(UITableWrapper).attrs({ $variant: 'default' })`
  .pool-row {
    cursor: pointer;
  }

  .pool-row:hover {
  }
`;

export { NameCell as PoolNameCell, ExpandIcon, NameText as PoolNameText };

export const PoolIcon = styled(StyledIcon).attrs(({ theme }) => ({
  as: DatabaseOutlined,
  $size: 'MD',
  $color: theme.colors.primary,
}))``;
