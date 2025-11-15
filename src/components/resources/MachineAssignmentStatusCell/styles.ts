import styled from 'styled-components'

export const StatusCellWrapper = styled.div<{ $align?: 'flex-start' | 'center' }>`
  display: flex;
  align-items: ${({ $align = 'flex-start' }) => $align};
  justify-content: ${({ $align = 'flex-start' }) =>
    $align === 'center' ? 'center' : 'flex-start'};
  min-height: 24px;
`
