import styled from 'styled-components'
import { Button, Checkbox, Collapse, Tag, Typography } from 'antd'
import { UploadOutlined, DownloadOutlined } from '@/utils/optimizedIcons'

const { Text } = Typography

export const TitleStack = styled.div`
  display: flex;
  flex-direction: column;
`

export const TitleText = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.LG}px;
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    line-height: ${({ theme }) => theme.lineHeight.TIGHT};
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`

export const SubtitleText = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    margin-top: ${({ theme }) => theme.spacing.XS}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`

export const SecondaryLabel = styled(Text)`
  && {
    margin-left: ${({ theme }) => theme.spacing.MD}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`

export const FooterLeftActions = styled.div`
  margin-right: auto;
`

export const ActionButton = styled(Button)`
  && {
    min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`

export const PrimaryActionButton = styled(ActionButton)`
  && {
    background-color: ${({ theme }) => theme.colors.primary};
    border-color: ${({ theme }) => theme.colors.primary};
    color: ${({ theme }) => theme.colors.textInverse};
  }
`

export const UploadIcon = styled(UploadOutlined)`
  font-size: ${({ theme }) => theme.dimensions.ICON_SM}px;
`

export const DownloadIcon = styled(DownloadOutlined)`
  font-size: ${({ theme }) => theme.dimensions.ICON_SM}px;
`

export const AutoSetupCheckbox = styled(Checkbox)`
  && {
    margin-right: auto;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    display: flex;
    align-items: center;
    min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
  }
`

export const TemplateCollapse = styled(Collapse)`
  margin: ${({ theme }) => `${theme.spacing.MD}px 0`};
`

export const SelectedTemplateTag = styled(Tag)`
  && {
    margin-left: ${({ theme }) => theme.spacing.SM}px;
  }
`
