import styled from 'styled-components';
import { Button, Empty, Table, Tag, Typography } from 'antd';
import { PrimaryButton as PrimitivePrimaryButton } from '@/styles/primitives';
import type { Repo } from '@/api/queries/repos';
const { Title, Text } = Typography;

export const SplitViewContainer = styled.div`
  display: flex;
  height: 100%;
  width: 100%;
  position: relative;
  overflow: hidden;
`;

export const LeftPanel = styled.div`
  flex: 1;
  height: 100%;
  overflow: auto;
  min-width: 0;
  background-color: ${({ theme }) => theme.colors.bgPrimary};
`;

export const Header = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.SM}px;
  padding: ${({ theme }) => `${theme.spacing.MD}px ${theme.spacing.XL}px`};
  border-bottom: 1px solid ${({ theme }) => theme.colors.borderSecondary};
`;

export const TitleRow = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const HeaderTitle = styled(Title).attrs({ level: 4 })`
  && {
    margin: 0;
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`;

export const TeamFilterTag = styled(Tag)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
    background-color: ${({ theme }) => theme.colors.bgSuccess};
    color: ${({ theme }) => theme.colors.success};
    border: none;
  }
`;

export const PrimaryButton = styled(PrimitivePrimaryButton)`
  && {
    gap: ${({ theme }) => theme.spacing.XS}px;
  }
`;

export const RepoLink = styled(Button).attrs({
  type: 'link',
})<{ $isSelected: boolean }>`
  && {
    padding: 0;
    height: auto;
    font-weight: ${({ theme, $isSelected }) => ($isSelected ? theme.fontWeight.SEMIBOLD : theme.fontWeight.REGULAR)};
  }
`;

export const GuidText = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    font-family: 'JetBrains Mono', 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  }
`;

export const TableSection = styled.div`
  padding: 0 ${({ theme }) => theme.spacing.XL}px;
`;

export const RepoTable = styled(Table<Repo>)`
  .ant-table {
    background-color: ${({ theme }) => theme.colors.bgPrimary};
  }

  .ant-table-tbody > tr {
    cursor: pointer;
  }

  .ant-table-tbody > tr.is-selected > td {
    background-color: ${({ theme }) => theme.colors.primaryBg};
  }
`;

export const EmptyState = styled(Empty)`
  && {
    margin: ${({ theme }) => `${theme.spacing.XL}px 0`};
  }
`;

export const ActionsButton = styled(Button)`
  && {
    display: inline-flex;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.XS}px;
    border-radius: ${({ theme }) => theme.borderRadius.MD}px;
  }
`;
