import styled from 'styled-components';

export const SourceLabel = styled.div`
  margin-bottom: 8px;
  font-weight: 500;
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
