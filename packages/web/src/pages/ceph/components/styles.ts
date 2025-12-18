import { FileImageOutlined } from '@ant-design/icons';
import { Card, Space } from 'antd';
import styled from 'styled-components';
import { RediaccButton, RediaccSelect } from '@/components/ui';

export const FullWidthSpace = styled(Space)`
  width: 100%;
`;

export const RemoveButton = styled(RediaccButton)`
`;

export const BulkActionsToolbar = styled.div`
  background: var(--color-fill-quaternary);
  display: flex;
  align-items: center;
  justify-content: space-between;
`;

export const BulkActionsLabel = styled.span`
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
`;

export const RightAlignedCol = styled.div`
  text-align: right;
`;

export const ImageIcon = styled(FileImageOutlined)`
  font-size: ${({ theme }) => theme.dimensions.ICON_MD}px;
`;

export const ImageName = styled.span`
`;

export const ExpandButton = styled(RediaccButton)`
  cursor: pointer;

  &:hover {
  }
`;

export const FiltersCard = styled(Card)`
`;

export const FullWidthSelect = styled(RediaccSelect)`
  width: 100%;
`;

export const TableContainer = styled.div`
  overflow: hidden;
`;

export const ImageListContainer = styled.div`
`;

export const CreateImageButton = styled(RediaccButton)`
  min-height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
`;
