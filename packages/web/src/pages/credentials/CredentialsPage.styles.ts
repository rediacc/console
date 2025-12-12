import { Alert, Tag } from 'antd';
import styled from 'styled-components';
import { InboxOutlined } from '@/utils/optimizedIcons';

// Inline list for modal content
export const InlineList = styled.ul`
  margin-top: ${({ theme }) => theme.spacing.SM}px;
  margin-bottom: 0;
  padding-left: 20px;
`;

// Section wrapper for affected resources display
export const AffectedSection = styled.div`
  margin-top: ${({ theme }) => theme.spacing.MD}px;
`;

// Alert with top margin for spacing
export const SpacedAlert = styled(Alert)`
  && {
    margin-top: ${({ theme }) => theme.spacing.MD}px;
  }
`;

// Repository icon with primary color
export const RepoIcon = styled(InboxOutlined)`
  color: ${({ theme }) => theme.colors.primary};
`;

// Secondary colored tag
export const SecondaryTag = styled(Tag)`
  && {
    background-color: ${({ theme }) => theme.colors.secondary};
    color: ${({ theme }) => theme.colors.bgPrimary};
    border-color: ${({ theme }) => theme.colors.secondary};
  }
`;

// Wrapper for team selector with constrained width
export const TeamSelectorWrapper = styled.div`
  width: 100%;
  max-width: 420px;
`;
