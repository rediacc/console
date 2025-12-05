import styled from 'styled-components';
import { Input, Select, Button } from 'antd';

export const Container = styled.div`
  padding: ${({ theme }) => theme.spacing.PAGE_CONTAINER}px 0;
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const ToolbarStack = styled.div`
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`;

export const FilterControls = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.SM}px;
`;

export const FilterInput = styled(Input)`
  && {
    width: min(320px, 100%);
    max-width: 100%;
  }
`;

export const AssignmentSelect = styled(Select)`
  && {
    width: min(240px, 100%);
  }
`;

export const PageSizeSelect = styled(Select)`
  && {
    width: min(200px, 100%);
  }
`;

export const RefreshButton = styled(Button)`
  && {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: ${({ theme }) => theme.spacing['6']}px;
    min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
  }
`;

export const StatusText = styled.div`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  color: ${({ theme }) => theme.colors.textSecondary};
`;

export const OptionLabel = styled.span`
  padding-right: ${({ theme }) => theme.spacing.LG}px;
`;
