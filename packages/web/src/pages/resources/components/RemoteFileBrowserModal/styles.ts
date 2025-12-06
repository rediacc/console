import styled from 'styled-components';
import { RediaccStack } from '@/components/ui';

export const ContentSpace = styled(RediaccStack).attrs({ direction: 'vertical' })`
  width: 100%;
`;

export const SourceLabel = styled.div`
  margin-bottom: 8px;
  font-weight: 500;
`;

export const SourceContainer = styled(RediaccStack).attrs({ direction: 'horizontal' })`
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
