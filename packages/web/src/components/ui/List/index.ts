import styled from 'styled-components';

export { RediaccList } from './RediaccList';
export { resolveListPadding } from './RediaccList.styles';
export type { ListSize, ListVariant, RediaccListProps } from './RediaccList.types';

export const ListTitleRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
`;

export const ListTitle = styled.span`
  font-size: ${({ theme }) => theme.fontSize.MD}px;
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  color: ${({ theme }) => theme.colors.textPrimary};
`;

export const ListSubtitle = styled.span`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  color: ${({ theme }) => theme.colors.textSecondary};
`;

export const BulletedList = styled.ul`
  padding-left: ${({ theme }) => theme.spacing.LG}px;
`;

export const InlineList = styled.ul`
  padding-left: ${({ theme }) => theme.spacing.LG}px;
`;

export const MutedList = styled(BulletedList)`
  color: ${({ theme }) => theme.colors.textSecondary};
  font-size: ${({ theme }) => theme.fontSize.SM}px;
`;

export const OrderedList = styled.ol`
  text-align: left;
  padding-left: ${({ theme }) => theme.spacing.LG}px;
`;

export const RequirementsList = styled(BulletedList)`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
`;

export const RegionsListWrapper = styled.div`
  .ant-table-tbody tr.clickable-row {
    cursor: pointer;
  }

  .ant-table-tbody tr.selected-row {
    background-color: ${({ theme }) => theme.colors.primaryBg};
  }

  .ant-table-tbody tr.selected-row:hover {
    background-color: ${({ theme }) => theme.colors.primaryBg};
  }
`;
