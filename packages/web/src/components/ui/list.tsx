/**
 * List components
 *
 * Components for list layouts and styling:
 * - ListTitleRow, ListTitle, ListSubtitle (for ResourceListView)
 * - BulletedList, OrderedList, InlineList, MutedList
 * - RequirementsList (specialized bulleted list)
 * - RegionsListWrapper (special case for infrastructure page)
 */

import styled from 'styled-components';

// ============================================
// LIST HEADER COMPONENTS
// ============================================

/**
 * ListTitleRow - Container for list title and subtitle
 * Use in ResourceListView title prop
 */
export const ListTitleRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const ListTitle = styled.span`
  font-size: ${({ theme }) => theme.fontSize.BASE}px;
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  color: ${({ theme }) => theme.colors.textPrimary};
`;

export const ListSubtitle = styled.span`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  color: ${({ theme }) => theme.colors.textSecondary};
`;

// ============================================
// LIST STYLES
// ============================================

export const BulletedList = styled.ul`
  margin: ${({ theme }) => theme.spacing.SM}px 0;
  padding-left: ${({ theme }) => theme.spacing.LG}px;
`;

export const InlineList = styled.ul`
  margin: ${({ theme }) => theme.spacing.XS}px 0;
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
  margin-top: ${({ theme }) => theme.spacing.SM}px;
`;

// ============================================
// SPECIAL CASE: REGIONS LIST
// ============================================

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
