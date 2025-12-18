import styled from 'styled-components';

export const SourceLabel = styled.div`
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
`;

export const SourceSelect = styled.div`
  width: ${({ theme }) => theme.dimensions.SOURCE_SELECT_WIDTH}px;
`;

export const SearchInput = styled.div`
  width: ${({ theme }) => theme.dimensions.SEARCH_INPUT_WIDTH_SM}px;
`;

export const FolderIcon = styled.span`
`;

export const FileIcon = styled.span`
`;

export const TooltipGuidText = styled.div`
  color: ${({ theme }) => theme.colors.textSecondary};
`;

export const FullWidthSelect = styled.div`
  width: 100%;
`;

export const LoadingPadding = styled.div`
`;
