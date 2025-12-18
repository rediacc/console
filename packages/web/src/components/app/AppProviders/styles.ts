import styled from 'styled-components';

export const ProvidersContainer = styled.div`
  min-height: 100vh;
  background-color: ${({ theme }) => theme.colors.bgPrimary};
  color: ${({ theme }) => theme.colors.textPrimary};
`;
