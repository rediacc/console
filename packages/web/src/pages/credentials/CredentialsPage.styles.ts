import { Alert, Tag } from 'antd';
import styled from 'styled-components';
import { InboxOutlined } from '@/utils/optimizedIcons';

// Inline list for modal content
export const InlineList = styled.ul`
  padding-left: ${({ theme }) => theme.spacing.LG}px;
`;

// Section wrapper for affected resources display
export const AffectedSection = styled.div`
`;

// Alert with top margin for spacing
export const SpacedAlert = styled(Alert)`
  && {
  }
`;

// Repository icon with primary color
export const RepoIcon = styled(InboxOutlined)`
  color: ${({ theme }) => theme.colors.primary};
`;

// Secondary colored tag
export const SecondaryTag = styled(Tag)`
  && {
    background-color: ${({ theme }) => theme.colors.textSecondary}; // Was secondary
    color: ${({ theme }) => theme.colors.bgPrimary};
  }
`;

// Wrapper for team selector with constrained width
export const TeamSelectorWrapper = styled.div`
  width: 100%;
  max-width: ${({ theme }) => theme.dimensions.SELECTOR_MAX_WIDTH}px;
`;
