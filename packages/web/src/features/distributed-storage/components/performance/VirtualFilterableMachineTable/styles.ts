import styled from 'styled-components';
import { Input, Select, Button } from 'antd';
import { FlexColumn } from '@/styles/primitives';
import { ActionGroup } from '@/components/common/styled';

export const Container = styled(FlexColumn).attrs({
  $gap: 'SM',
})`
  padding: ${({ theme }) => theme.spacing.PAGE_CONTAINER}px 0;
`;

export const ToolbarStack = styled(FlexColumn).attrs({
  $gap: 'SM',
})`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`;

export const FilterControls = styled(ActionGroup)``;

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
    min-width: ${({ theme }) => theme.spacing.XXXL}px;
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
