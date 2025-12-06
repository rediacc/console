import styled from 'styled-components';
import { CopyOutlined, CloudUploadOutlined } from '@ant-design/icons';
import { RediaccBadge } from '@/components/ui';
import {
  FlexColumn,
  EmptyStateWrapper,
  TableCellText,
  StyledIcon,
  IconActionButton,
} from '@/styles/primitives';
import { RediaccTag, RediaccButton, RediaccStack } from '@/components/ui';
import { TableWrapper, NameCell, ActionsRow } from '../../styles/tableAliases';

export const Container = styled(FlexColumn).attrs({ $gap: 'MD' })`
  padding: ${({ theme }) =>
    `${theme.spacing.MD}px ${theme.spacing.MD}px ${theme.spacing.MD}px ${theme.spacing.LG}px`};
  background: var(--color-fill-quaternary);
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
`;

export const Title = styled.h5`
  margin: 0;
  font-size: ${({ theme }) => theme.fontSize.H5}px;
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  color: ${({ theme }) => theme.colors.textPrimary};
`;

export { ActionsRow, TableWrapper, NameCell };

export const ExpandButton = styled(IconActionButton)`
  margin-right: ${({ theme }) => theme.spacing.SM}px;
`;

export const CloneIcon = styled(StyledIcon).attrs(({ theme }) => ({
  as: CopyOutlined,
  $size: 'MD',
  $color: theme.colors.textSecondary,
}))``;

export const CloneName = styled(TableCellText)`
  font-size: ${({ theme }) => theme.fontSize.BASE}px;
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
`;

export const VaultTag = styled(RediaccTag).attrs({
  variant: 'neutral',
  size: 'sm',
})``;

export const MachineCountBadgeWrapper = styled(RediaccBadge)<{ $active?: boolean }>`
  .ant-badge-count {
    background-color: ${({ $active }) =>
      $active ? 'var(--color-primary)' : 'var(--color-fill-tertiary)'};
    color: ${({ $active }) => ($active ? 'var(--color-white)' : 'var(--color-text-secondary)')};
    box-shadow: none;
    min-width: ${({ theme }) => theme.spacing.MD}px;
  }

  .anticon {
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`;

export const MachineListWrapper = styled.div`
  padding: ${({ theme }) => theme.spacing.MD}px;
`;

export const MachineListStack = styled(RediaccStack).attrs({
  direction: 'vertical',
  gap: 'md',
})`
  width: 100%;
`;

export { ActionsRow as MachineListHeader };

export const MachineCountTag = styled(RediaccTag).attrs({
  variant: 'neutral',
  size: 'sm',
})``;

export const MachineTagGrid = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.XS}px;
`;

export const MachineTag = styled(RediaccTag).attrs({
  preset: 'machine',
  size: 'sm',
})``;

export const MachineListButton = styled(RediaccButton)`
  && {
    align-self: flex-start;
  }
`;

export const MachineListActions = styled(RediaccStack).attrs({ direction: 'horizontal' })`
  width: 100%;
`;

export const EmptyState = styled(EmptyStateWrapper)`
  padding: ${({ theme }) => `${theme.spacing.LG}px ${theme.spacing.MD}px`};
`;

export const AssignButton = styled(RediaccButton)`
  && {
    min-width: ${({ theme }) => theme.spacing.XXXL}px;
  }
`;

export const RemoteIcon = styled(StyledIcon).attrs(({ theme }) => ({
  as: CloudUploadOutlined,
  $size: theme.fontSize.BASE,
}))``;
