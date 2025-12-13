import { FileImageOutlined } from '@ant-design/icons';
import { Card, Space } from 'antd';
import styled from 'styled-components';
import { RediaccButton, RediaccSelect } from '@/components/ui';

export const FullWidthSpace = styled(Space)`
  width: 100%;
`;

export const RemoveButton = styled(RediaccButton)`
  margin-left: ${({ theme }) => theme.spacing.SM}px;
`;

export const BulkActionsToolbar = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  padding: ${({ theme }) => theme.spacing.MD}px;
  background: var(--color-fill-quaternary);
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
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
  color: ${({ theme }) => theme.colors.primary};
`;

export const ImageName = styled.span`
  color: ${({ theme }) => theme.colors.textPrimary};
`;

export const ExpandButton = styled(RediaccButton)`
  margin-right: ${({ theme }) => theme.spacing.SM}px;
  border-radius: ${({ theme }) => theme.borderRadius.MD}px;
  border: none;
  background: transparent;
  cursor: pointer;
  transition: ${({ theme }) => theme.transitions.BUTTON};

  &:hover {
    background: var(--color-fill-tertiary);
  }
`;

export const FiltersCard = styled(Card)`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`;

export const FullWidthSelect = styled(RediaccSelect)`
  width: 100%;
`;

export const TableContainer = styled.div`
  overflow: hidden;
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
`;

export const ImageListContainer = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`;

export const CreateImageButton = styled(RediaccButton)`
  border-radius: ${({ theme }) => theme.borderRadius.MD}px;
  min-height: ${({ theme }) => theme.dimensions.FORM_CONTROL_HEIGHT}px;
`;
