import { Typography } from 'antd';
import styled from 'styled-components';

const { Title } = Typography;

export const Container = styled.div`
  overflow-x: auto;
  position: relative;
`;

export const ContainersSection = styled.div`
`;

export const PluginContainersSection = styled(ContainersSection)`
`;

export const EmptyState = styled.div`
  text-align: center;
`;

/** Wrapper for repository container table row styling */
export const TableStyleWrapper = styled.div`
  .repository-container-row--clickable {
    cursor: pointer;
  }

  .repository-container-row--clickable:hover td {
  }

  .repository-container-row--selected td {
  }
`;

export const SectionTitle = styled(Title)`
  && {
  }
`;
