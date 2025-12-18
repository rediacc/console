import styled from 'styled-components';
import { RediaccBadge, RediaccTag } from '@/components/ui';
import { borderedCard } from '@/styles/mixins';

export const TableContainer = styled.div`
  width: 100%;
  overflow: hidden;
  ${borderedCard()}

  .ant-table {
  }

  .ant-table-thead > tr > th {
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }

  .ant-table-tbody > tr > td {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`;

export const ExpandedRowContent = styled.div`
`;

export const AssignmentTag = styled(RediaccTag).attrs({
  variant: 'info',
  size: 'sm',
})`
  && {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    line-height: ${({ theme }) => theme.lineHeight.NORMAL};
  }
`;

export const QueueBadge = styled(RediaccBadge)<{ $hasItems: boolean }>`
  && {
    .ant-badge-count {
      min-width: ${({ theme }) => theme.spacing.LG}px;
      font-size: ${({ theme }) => theme.fontSize.SM}px;
      font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
      line-height: ${({ theme }) => theme.lineHeight.TIGHT};
    }
  }
`;
