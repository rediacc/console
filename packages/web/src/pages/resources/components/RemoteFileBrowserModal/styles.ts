import styled from 'styled-components';

export const SourceLabel = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.SM}px;
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
`;

export const SourceSelect = styled.div`
  width: 300px;
`;

export const SearchInput = styled.div`
  width: 250px;
`;

export const FolderIcon = styled.span`
  color: ${({ theme }) => theme.colors.primary};
`;

export const FileIcon = styled.span`
  color: ${({ theme }) => theme.colors.textSecondary};
`;

export const TooltipGuidText = styled.div`
  margin-top: ${({ theme }) => theme.spacing.XS}px;
  opacity: 0.85;
`;

export const FullWidthSelect = styled.div`
  width: 100%;
`;

export const LoadingPadding = styled.div`
  padding: ${({ theme }) => theme.spacing.SM}px;
`;
