import styled from 'styled-components';
import { Badge, Button, Space, Tag } from 'antd';
import { CopyOutlined, CloudUploadOutlined } from '@ant-design/icons';
import {
  EmptyStateWrapper,
  IconButton as BaseIconButton,
  TableContainer as BaseTableContainer,
  TableCellContent,
  TableCellText,
  StyledIcon,
} from '@/styles/primitives';

export const Container = styled.div`
  padding: ${({ theme }) =>
    `${theme.spacing.MD}px ${theme.spacing.MD}px ${theme.spacing.MD}px ${theme.spacing.LG}px`};
  background: var(--color-fill-quaternary);
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.MD}px;
`;

export const Title = styled.h5`
  margin: 0;
  font-size: ${({ theme }) => theme.fontSize.H5}px;
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  color: ${({ theme }) => theme.colors.textPrimary};
`;

export const ActionsRow = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const CreateButton = styled(Button)`
  && {
    min-width: ${({ theme }) => theme.spacing.XXXL}px;
    min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_SM}px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
`;

export const TableWrapper = styled(BaseTableContainer)``;

export const IconActionButton = styled(BaseIconButton)`
  && {
    width: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_SM}px;
    height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_SM}px;
    min-width: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_SM}px;
    min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_SM}px;
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    border: none;
    box-shadow: none;

    &:hover,
    &:focus {
      background: var(--color-fill-tertiary);
    }
  }
`;

export const ExpandButton = styled(IconActionButton)`
  margin-right: ${({ theme }) => theme.spacing.SM}px;
`;

export const NameCell = styled(TableCellContent)``;

export const CloneIcon = styled(StyledIcon).attrs(({ theme }) => ({
  as: CopyOutlined,
  $size: 'MD',
  $color: theme.colors.textSecondary,
}))``;

export const CloneName = styled(TableCellText)`
  font-size: ${({ theme }) => theme.fontSize.BASE}px;
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
`;

export const VaultTag = styled(Tag)`
  border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
`;

export const MachineCountBadgeWrapper = styled(Badge)<{ $active?: boolean }>`
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

export const MachineListStack = styled(Space).attrs({
  orientation: 'vertical',
  size: 'middle',
})`
  width: 100%;
`;

export const MachineListHeader = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const MachineCountTag = styled(Tag)`
  border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  background: var(--color-fill-tertiary);
`;

export const MachineTagGrid = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.XS}px;
`;

export const MachineTag = styled(Tag)`
  border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  padding: 0 ${({ theme }) => theme.spacing.XS}px;
`;

export const MachineListButton = styled(Button)`
  && {
    align-self: flex-start;
  }
`;

export const MachineListActions = styled(Space)`
  width: 100%;
`;

export const EmptyState = styled(EmptyStateWrapper)`
  padding: ${({ theme }) => `${theme.spacing.LG}px ${theme.spacing.MD}px`};
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
  align-items: center;
`;

export const AssignButton = styled(Button)`
  && {
    min-width: ${({ theme }) => theme.spacing.XXXL}px;
  }
`;

export const RemoteIcon = styled(StyledIcon).attrs(({ theme }) => ({
  as: CloudUploadOutlined,
  $size: theme.fontSize.BASE,
}))``;
