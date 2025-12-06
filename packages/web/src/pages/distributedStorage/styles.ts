import styled from 'styled-components';
import { Typography } from 'antd';
import {
  PageContainer,
  SectionStack,
  SectionHeaderRow,
  EmptyStateWrapper,
} from '@/styles/primitives';
import { ActionGroup as BaseActionGroup } from '@/components/common/styled';

const { Title } = Typography;

export const PageWrapper = PageContainer;
export const HeaderSection = SectionStack;
export const HeaderRow = SectionHeaderRow;

export const TitleGroup = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.MD}px;
  flex: 1 1 auto;
  min-width: 0;
`;

export const HeaderTitle = styled(Title)`
  && {
    margin: 0;
  }
`;

export const TeamSelectorWrapper = styled.div`
  flex: 1 1 auto;
  min-width: ${({ theme }) => theme.dimensions.CARD_WIDTH}px;
  max-width: ${({ theme }) => theme.dimensions.CARD_WIDTH_LG}px;

  > * {
    width: 100%;
  }
`;

export const ActionGroup = styled(BaseActionGroup)`
  flex-shrink: 0;
`;

export const EmptyState = EmptyStateWrapper;
