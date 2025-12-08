import { Link } from 'react-router-dom';
import styled from 'styled-components';

export const StyledLanguageLink = styled(Link)`
  color: ${({ theme }) => theme.colors.textPrimary};
  text-decoration: none;
  transition: ${({ theme }) => theme.transitions.DEFAULT};

  &:hover {
    color: ${({ theme }) => theme.colors.primary};
    text-decoration: underline;
  }
`;
