import { Typography } from 'antd';
import styled from 'styled-components';
import { RediaccTag, RediaccSelect } from '@/components/ui';
import { FlexRow } from '@/styles/primitives';

const { Text: AntText } = Typography;

export const StyledSelect = styled(RediaccSelect).attrs({
  size: 'sm',
  fullWidth: true,
})`
  && .ant-select-selector {
    padding: 0 ${({ theme }) => theme.spacing.SM}px;
  }
`;

export const OptionContent = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.MD}px;
  width: 100%;
`;

export const MachineMeta = styled.div`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
  flex-wrap: wrap;
`;

export const MachineIcon = styled.span`
  display: inline-flex;
  align-items: center;
  color: ${({ theme }) => theme.colors.primary};
  font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
`;

export const MachineName = styled(AntText)<{ $dimmed?: boolean }>`
  && {
    color: ${({ theme }) => theme.colors.textPrimary};
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    opacity: ${({ $dimmed }) => ($dimmed ? 0.6 : 1)};
  }
`;

export const TeamTag = styled(RediaccTag).attrs({
  preset: 'team',
  size: 'sm',
  borderless: true,
})`
  && {
    padding: 0 ${({ theme }) => theme.spacing.SM}px;
  }
`;

export const BridgeTag = styled(RediaccTag).attrs({
  preset: 'bridge',
  size: 'sm',
  borderless: true,
})`
  && {
    padding: 0 ${({ theme }) => theme.spacing.SM}px;
  }
`;

export const StatusContainer = styled(FlexRow)`
  margin-left: auto;
`;

export const StatusIcon = styled.span`
  display: inline-flex;
  align-items: center;
  font-size: ${({ theme }) => theme.dimensions.ICON_SM}px;
`;

export const SpinnerWrapper = styled(FlexRow).attrs({ $justify: 'center' })`
  width: 100%;
  padding: ${({ theme }) => theme.spacing.LG}px 0;
`;

export const EmptyDescription = styled(AntText)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`;
