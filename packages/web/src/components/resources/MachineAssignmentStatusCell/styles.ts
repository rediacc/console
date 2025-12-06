import styled from 'styled-components';
import { FlexRow } from '@/styles/primitives';

export const StatusCellWrapper = styled(FlexRow)<{ $align?: 'flex-start' | 'center' }>`
  align-items: ${({ $align = 'flex-start' }) => $align};
  justify-content: ${({ $align = 'flex-start' }) =>
    $align === 'center' ? 'center' : 'flex-start'};
  min-height: 24px;
`;
