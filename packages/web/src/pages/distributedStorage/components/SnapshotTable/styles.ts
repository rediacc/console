import styled from 'styled-components';
import { Button, Tag } from 'antd';
import { CameraOutlined } from '@ant-design/icons';
import {
  FlexColumn,
  FlexRow,
  IconButton as BaseIconButton,
  TableContainer as BaseTableContainer,
  TableCellContent,
  TableCellText,
  StyledIcon,
} from '@/styles/primitives';

export const Container = styled(FlexColumn).attrs({ $gap: 'MD' })`
  padding: ${({ theme }) => theme.spacing.MD}px;
  background: var(--color-fill-quaternary);
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
`;

export const Title = styled.h4`
  margin: 0;
  font-size: ${({ theme }) => theme.fontSize.H4}px;
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  color: ${({ theme }) => theme.colors.textPrimary};
`;

export const ActionsRow = styled(FlexRow).attrs({ $gap: 'XS', $justify: 'flex-start' })``;

export const CreateButton = styled(Button)`
  && {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_SM}px;
    min-width: ${({ theme }) => theme.spacing.XXXL}px;
  }
`;

export const TableWrapper = styled(BaseTableContainer)``;

export const NameCell = styled(TableCellContent)``;

export const NameIcon = styled(StyledIcon).attrs(({ theme }) => ({
  as: CameraOutlined,
  $size: 'MD',
  $color: theme.colors.primary,
}))``;

export const NameText = styled(TableCellText)`
  font-size: ${({ theme }) => theme.fontSize.BASE}px;
`;

export const VaultTag = styled(Tag)`
  border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
`;

export const GuidText = styled.span`
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
  color: ${({ theme }) => theme.colors.textSecondary};
`;

const IconButton = styled(BaseIconButton)`
  && {
    width: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_SM}px;
    height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_SM}px;
    min-width: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_SM}px;
    min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_SM}px;
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    border: none;
    background: transparent;
    box-shadow: none;
    color: ${({ theme }) => theme.colors.textPrimary};
    transition: background ${({ theme }) => theme.transitions.FAST};

    &:hover,
    &:focus {
      background: var(--color-fill-tertiary);
    }
  }
`;

export const ExpandButton = styled(IconButton)`
  margin-right: ${({ theme }) => theme.spacing.SM}px;
`;
