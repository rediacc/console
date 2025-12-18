import { Typography } from 'antd';
import styled from 'styled-components';
import { ActionGroup as BaseActionGroup } from '@/components/common/styled';

const { Title } = Typography;

export const TitleGroup = styled.div`
  display: flex;
  align-items: center;
  flex: 1 1 auto;
  min-width: 0;
`;

export const HeaderTitle = styled(Title)`
  && {
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

/**
 * Prevent action buttons from shrinking when team selector takes space
 * in the space-between header layout (TitleGroup grows, ActionGroup stays fixed)
 */
export const ActionGroup = styled(BaseActionGroup)`
  flex-shrink: 0;
`;
