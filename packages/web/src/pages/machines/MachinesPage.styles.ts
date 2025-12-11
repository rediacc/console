import styled from 'styled-components';
import { Empty } from 'antd';
import TeamSelector from '@/components/common/TeamSelector';

export const EmptyState = styled(Empty)`
  && {
    padding: ${({ theme }) => theme.spacing.LG}px 0;
  }
`;

export const StyledTeamSelector = styled(TeamSelector)`
  && {
    width: 100%;
  }
`;
