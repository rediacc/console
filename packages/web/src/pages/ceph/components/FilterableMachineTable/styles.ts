import styled from 'styled-components';
import { RediaccBadge, RediaccTag } from '@/components/ui';
import { borderedCard } from '@/styles/mixins';

export const TableContainer = styled.div`
  width: 100%;
  overflow: hidden;
  ${borderedCard()}
  background: ${({ theme }) => theme.colors.bgPrimary};

  .ant-table {
    background: transparent;
  }

  .ant-table-thead > tr > th {
    background: ${({ theme }) => theme.colors.bgTertiary};
    color: ${({ theme }) => theme.colors.textSecondary};
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    border-bottom: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  }

  .ant-table-tbody > tr > td {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    padding: ${({ theme }) => theme.spacing.SM}px ${({ theme }) => theme.spacing.MD}px;
  }
`;

export const ExpandedRowContent = styled.div`
  padding: ${({ theme }) => theme.spacing.MD}px;
  background: ${({ theme }) => theme.colors.bgTertiary};
  border-radius: ${({ theme }) => theme.borderRadius.MD}px;
`;

export const AssignmentTag = styled(RediaccTag).attrs({
  variant: 'info',
  size: 'sm',
  borderless: true,
})`
  && {
    margin: 0;
    background: ${({ theme }) => theme.colors.bgSelected};
    color: ${({ theme }) => theme.colors.textSelected};
    padding: 0 ${({ theme }) => theme.spacing.XS}px;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    line-height: ${({ theme }) => theme.lineHeight.NORMAL};
  }
`;

export const QueueBadge = styled(RediaccBadge)<{ $hasItems: boolean }>`
  && {
    .ant-badge-count {
      min-width: ${({ theme }) => theme.spacing.LG}px;
      padding: 0 ${({ theme }) => theme.spacing.XS}px;
      border-radius: ${({ theme }) => theme.borderRadius.SM}px;
      background: ${({ theme, $hasItems }) =>
        $hasItems ? theme.colors.success : theme.colors.bgTertiary};
      color: ${({ theme, $hasItems }) =>
        $hasItems ? theme.colors.textInverse : theme.colors.textSecondary};
      font-size: ${({ theme }) => theme.fontSize.SM}px;
      font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
      line-height: ${({ theme }) => theme.lineHeight.TIGHT};
    }
  }
`;
