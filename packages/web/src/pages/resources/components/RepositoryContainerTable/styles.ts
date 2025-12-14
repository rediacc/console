import { Typography } from 'antd';
import styled from 'styled-components';

const { Title } = Typography;

export const Container = styled.div`
  overflow-x: auto;
  position: relative;
`;

export const ContainersSection = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.LG}px;
`;

export const PluginContainersSection = styled(ContainersSection)`
  margin-top: ${({ theme }) => theme.spacing.LG}px;
`;

export const EmptyState = styled.div`
  padding: ${({ theme }) => theme.spacing.XXL}px 0;
  text-align: center;
`;

/** Wrapper for repository container table row styling */
export const TableStyleWrapper = styled.div`
  .repository-container-row td {
    transition: background-color ${({ theme }) => theme.transitions.DEFAULT};
  }

  .repository-container-row--clickable {
    cursor: pointer;
  }

  .repository-container-row--clickable:hover td {
    background-color: ${({ theme }) => theme.colors.bgHover};
  }

  .repository-container-row--selected td {
    background-color: ${({ theme }) => theme.colors.primaryBg};
  }
`;

export const SectionTitle = styled(Title)`
  && {
    margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  }
`;
