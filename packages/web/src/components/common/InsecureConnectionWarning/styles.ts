import styled from 'styled-components';

export const WarningDescription = styled.div`
  color: ${({ theme }) => theme.colors.textSecondary};
  font-size: ${({ theme }) => theme.fontSize.SM}px;

  p {
    margin: 0 0 ${({ theme }) => theme.spacing.XS}px 0;
  }
`;

export const ResolutionText = styled.p`
  && {
    margin: ${({ theme }) => theme.spacing.XS}px 0 0 0;
    padding: ${({ theme }) => theme.spacing.XS}px;
    background-color: ${({ theme }) => theme.colors.bgSecondary};
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
    font-size: ${({ theme }) => theme.fontSize.XS}px;
  }
`;

export const StyledAlert = styled.div`
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  border: 2px solid var(--rediacc-color-error);
  background-color: var(--rediacc-color-bg-error);
`;
