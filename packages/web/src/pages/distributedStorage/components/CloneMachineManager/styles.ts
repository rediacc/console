import styled from 'styled-components';
import { Card, Row, Input, Button, Statistic, Typography } from 'antd';
import { CopyOutlined, TeamOutlined, DesktopOutlined } from '@/utils/optimizedIcons';
import {
  IconButton as BaseIconButton,
  PillTag,
  StyledIcon,
  TableContainer as BaseTableContainer,
  TableCellContent,
  TableCellText,
} from '@/styles/primitives';

const { Title, Text } = Typography;

export const ManagerCard = styled(Card)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
    box-shadow: ${({ theme }) => theme.shadows.CARD};
    background: ${({ theme }) => theme.colors.bgPrimary};
  }
`;

export const HeaderRow = styled(Row)`
  margin-bottom: ${({ theme }) => theme.spacing.LG}px;
`;

export const HeaderContent = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.XS}px;
`;

export const TitleRow = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const TitleIcon = styled(StyledIcon).attrs(({ theme }) => ({
  as: CopyOutlined,
  $size: 'MD',
  $color: theme.colors.primary,
}))``;

export const TitleText = styled(Title).attrs({ level: 4 })`
  && {
    margin: 0;
    color: ${({ theme }) => theme.colors.textPrimary};
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    display: flex;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.XS}px;
  }
`;

export const CloneName = styled.span`
  color: ${({ theme }) => theme.colors.textPrimary};
`;

export const MetadataText = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`;

export const StatsRow = styled(Row)`
  height: 100%;
`;

export const StatCard = styled(Statistic)<{ $highlight?: boolean }>`
  && {
    .ant-statistic-title {
      color: ${({ theme }) => theme.colors.textSecondary};
      margin-bottom: ${({ theme }) => theme.spacing.XS}px;
    }

    .ant-statistic-content-value {
      font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
      color: ${({ theme, $highlight }) =>
        $highlight ? theme.colors.primary : theme.colors.textPrimary};
    }
  }
`;

export const StatIcon = styled(StyledIcon).attrs(({ theme }) => ({
  as: TeamOutlined,
  $size: 'MD',
  $color: theme.colors.textSecondary,
}))``;

export const ToolbarRow = styled(Row)`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  row-gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const ActionButtonGroup = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const ToolbarButton = styled(BaseIconButton)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
  }
`;

export const SearchInput = styled(Input.Search)`
  && {
    width: 320px;
    max-width: 100%;
  }
`;

export const WarningWrapper = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`;

export const TableContainer = styled(BaseTableContainer)``;

export const EmptyActionButton = styled(Button)`
  && {
    margin-top: ${({ theme }) => theme.spacing.SM}px;
  }
`;

export const ModalStack = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.LG}px;
`;

export const ModalPlaceholder = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  padding: ${({ theme }) => theme.spacing.XL}px;
`;

export const SelectedCountTag = styled(PillTag).attrs({
  $variant: 'primary',
  $size: 'SM',
})`
  && {
    align-self: flex-start;
  }
`;

export const ModalTitle = styled.span`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
  font-size: ${({ theme }) => theme.fontSize.BASE}px;
  color: ${({ theme }) => theme.colors.textPrimary};
`;

export const ModalTitleIcon = styled(StyledIcon).attrs(({ theme }) => ({
  as: TeamOutlined,
  $size: 'MD',
  $color: theme.colors.textSecondary,
}))``;

export const MachineNameCell = styled(TableCellContent)``;

export const MachineNameIcon = styled(StyledIcon).attrs(({ theme }) => ({
  as: DesktopOutlined,
  $size: 'MD',
  $color: theme.colors.primary,
}))``;

export const MachineName = styled(TableCellText)``;

export const BridgeTag = styled(PillTag).attrs({
  $variant: 'team',
  $size: 'SM',
})``;
