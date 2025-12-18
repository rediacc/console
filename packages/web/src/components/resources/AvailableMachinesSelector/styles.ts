import { Typography } from 'antd';
import styled from 'styled-components';
import { RediaccSelect, RediaccTag } from '@/components/ui';
import { FlexRow } from '@/styles/primitives';

const { Text: AntText } = Typography;

export const StyledSelect = styled(RediaccSelect).attrs({
  size: 'sm',
  fullWidth: true,
})`
  && .ant-select-selector {
  }
`;

export const OptionContent = styled.div`
  display: flex;
  align-items: center;
  width: 100%;
`;

export const MachineMeta = styled.div`
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
`;

export const MachineIcon = styled.span`
  display: inline-flex;
  align-items: center;
  font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
`;

export const MachineName = styled(AntText)<{ $dimmed?: boolean }>`
  && {
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    color: ${({ $dimmed, theme }) => ($dimmed ? theme.colors.textSecondary : theme.colors.textPrimary)};
  }
`;

export const TeamTag = styled(RediaccTag).attrs({
  preset: 'team',
  size: 'sm',
  borderless: true,
})`
  && {
  }
`;

export const BridgeTag = styled(RediaccTag).attrs({
  preset: 'bridge',
  size: 'sm',
  borderless: true,
})`
  && {
  }
`;

export const StatusContainer = styled(FlexRow)`
`;

export const SpinnerWrapper = styled(FlexRow).attrs({ $justify: 'center' })`
  width: 100%;
`;

export const EmptyDescription = styled(AntText)`
  && {
  }
`;
