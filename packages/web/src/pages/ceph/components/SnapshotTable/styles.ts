import { CameraOutlined } from '@ant-design/icons';
import styled from 'styled-components';
import { NameText as BaseNameText, NameCell, TableWrapper } from '@/pages/ceph/styles/tableAliases';
import { FlexColumn, FlexRow, IconActionButton, StyledIcon } from '@/styles/primitives';

export const Container = styled(FlexColumn).attrs({})`
`;

export const Title = styled.h4`
  font-size: ${({ theme }) => theme.fontSize.XL}px;
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
`;

export const ActionsRow = styled(FlexRow).attrs({ $justify: 'flex-start' })``;

export { TableWrapper, NameCell };

export const NameIcon = styled(StyledIcon).attrs(({ theme }) => ({
  as: CameraOutlined,
  $size: 'MD',
  $color: theme.colors.primary,
}))``;

export const NameText = styled(BaseNameText)`
  font-size: ${({ theme }) => theme.fontSize.MD}px;
`;

// VaultTag removed - use <RediaccTag variant="neutral" compact> directly

export const GuidText = styled.span`
  font-family: ${({ theme }) => theme.fontFamily.MONO};
  font-size: ${({ theme }) => theme.fontSize.XS}px;
`;

export const ExpandButton = styled(IconActionButton)`
`;
