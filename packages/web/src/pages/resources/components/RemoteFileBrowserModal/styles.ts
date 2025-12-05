import styled from 'styled-components';
import { Space } from 'antd';

export const ContentSpace = styled(Space)`
  width: 100%;
`;

export const SourceLabel = styled.div`
  margin-bottom: 8px;
  font-weight: 500;
`;

export const SourceContainer = styled(Space)`
  width: 100%;
  justify-content: space-between;
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
