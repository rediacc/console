import styled, { type DefaultTheme } from 'styled-components'
import { Card, Badge, Empty, Alert, Form, Select, Input, Typography, Space } from 'antd'
import {
  PageContainer,
  SectionHeaderRow as PrimitiveHeaderRow,
  ActionButton as PrimitiveActionButton,
} from '@/styles/primitives'
import { DESIGN_TOKENS } from '@/utils/styleConstants'

const { Title, Text } = Typography
const SpaceCompact = Space.Compact

type IconSize = 'sm' | 'md' | 'lg'

const getIconSize = (size: IconSize, theme: DefaultTheme) => {
  switch (size) {
    case 'sm':
      return `${theme.dimensions.ICON_SM}px`
    case 'lg':
      return `${theme.dimensions.ICON_LG}px`
    default:
      return `${theme.dimensions.ICON_MD}px`
  }
}

export const ACTIONS_COLUMN_WIDTH = DESIGN_TOKENS.DIMENSIONS.MODAL_WIDTH

export const PageWrapper = styled(PageContainer)`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.XL}px;
`

export const SectionStack = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.LG}px;
  width: 100%;
  margin-bottom: ${({ theme }) => theme.spacing.LG}px;
`

export const SectionHeading = styled(Title)`
  && {
    margin: 0 0 ${({ theme }) => theme.spacing.LG}px;
  }
`

export const SettingsCard = styled(Card)`
  height: 100%;
`

export const CardContent = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.MD}px;
  width: 100%;
`

export const CardHeader = styled.div`
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const CardTitle = styled(Title)`
  && {
    margin: 0;
  }
`

export const CardDescription = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`

export const CardActions = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
  margin-top: ${({ theme }) => theme.spacing.MD}px;
`

export const ListTitleRow = styled.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const ListTitle = styled.span`
  font-size: ${({ theme }) => theme.fontSize.BASE}px;
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  color: ${({ theme }) => theme.colors.textPrimary};
`

export const ListSubtitle = styled.span`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  color: ${({ theme }) => theme.colors.textSecondary};
`

export const IconWrapper = styled.span<{ $size?: IconSize; $tone?: 'primary' | 'inherit' }>`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: ${({ theme, $size = 'md' }) => getIconSize($size, theme)};
  color: ${({ theme, $tone = 'primary' }) => ($tone === 'primary' ? theme.colors.primary : 'currentColor')};
`

export const PrimaryBadge = styled(Badge)`
  .ant-scroll-number {
    background-color: ${({ theme }) => theme.colors.primary};
  }
`

export const RegionsSection = styled.section`
  margin-top: ${({ theme }) => theme.spacing['6']}px;
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.LG}px;
`

export const RegionsListWrapper = styled.div`
  .ant-table-tbody tr.clickable-row {
    cursor: pointer;
  }

  .ant-table-tbody tr.selected-row {
    background-color: ${({ theme }) => theme.colors.primaryBg};
  }

  .ant-table-tbody tr.selected-row:hover {
    background-color: ${({ theme }) => theme.colors.primaryBg};
  }
`

export const CardHeaderRow = styled(PrimitiveHeaderRow)`
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`

export const SecondaryText = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`

export const PaddedEmpty = styled(Empty)`
  padding: ${({ theme }) => theme.spacing['5']}px 0;
`

export const CenteredState = styled.div`
  width: 100%;
  text-align: center;
  padding: ${({ theme }) => theme.spacing['6']}px 0;
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
  align-items: center;
  justify-content: center;
  color: ${({ theme }) => theme.colors.textSecondary};
`

export const LoadingHint = styled(Text)`
  && {
    display: block;
    margin-top: ${({ theme }) => theme.spacing.SM}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`

export const ModalStack = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.MD}px;
  width: 100%;
`

export const ModalStackLarge = styled(ModalStack)`
  gap: ${({ theme }) => theme.spacing.LG}px;
`

export const InlineFormRow = styled.div`
  width: 100%;
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.SM}px;
  align-items: flex-start;
`

export const FullWidthSelect = styled(Select)`
  width: 100%;
  flex: 1 1 240px;
  min-width: 200px;
`

export const FullWidthInput = styled(Input)`
  width: 100%;
  flex: 1 1 240px;
  min-width: 200px;
`

export const TokenCopyRow = styled(SpaceCompact)`
  width: 100%;
  margin-top: ${({ theme }) => theme.spacing.SM}px;
`

export const ModalAlert = styled(Alert)`
  margin-bottom: ${({ theme }) => theme.spacing.LG}px;
`

export const FormItemSpaced = styled(Form.Item)`
  && {
    margin-bottom: ${({ theme }) => theme.spacing.LG}px;
  }
`

export const FormItemNoMargin = styled(Form.Item)`
  && {
    margin-bottom: 0;
  }
`

export const FormItemActions = styled(Form.Item)`
  && {
    margin: ${({ theme }) => theme.spacing.LG}px 0 0;
  }
`

export const FormItemActionsLg = styled(Form.Item)`
  && {
    margin: ${({ theme }) => theme.spacing.XL}px 0 0;
  }
`

export const ModalActions = styled.div`
  width: 100%;
  display: flex;
  justify-content: flex-end;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const DangerSection = styled.section`
  margin-top: ${({ theme }) => theme.spacing['6']}px;
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.LG}px;
`

export const DangerHeading = styled(Title)`
  && {
    margin: 0 0 ${({ theme }) => theme.spacing.LG}px;
    color: ${({ theme }) => theme.colors.error};
    display: flex;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.SM}px;
  }
`

export const DangerCard = styled(Card)`
  border-color: ${({ theme }) => theme.colors.error};
`

export const DangerStack = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.LG}px;
  width: 100%;
`

export const RightAlign = styled.div`
  width: 100%;
  display: flex;
  justify-content: flex-end;
  text-align: right;
  gap: ${({ theme }) => theme.spacing.SM}px;
  flex-wrap: wrap;
`

export const DangerDivider = styled.hr`
  border: none;
  border-top: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  margin: 0;
`

export const BulletedList = styled.ul`
  margin: ${({ theme }) => theme.spacing.SM}px 0;
  padding-left: ${({ theme }) => theme.spacing.LG}px;
`

export const InlineList = styled.ul`
  margin: ${({ theme }) => theme.spacing.XS}px 0;
  padding-left: ${({ theme }) => theme.spacing.LG}px;
`

export const MutedList = styled(BulletedList)`
  color: ${({ theme }) => theme.colors.textSecondary};
  font-size: ${({ theme }) => theme.fontSize.SM}px;
`

export const WarningNote = styled(Text)`
  && {
    display: block;
    margin-top: ${({ theme }) => theme.spacing.SM}px;
  }
`

export const DangerText = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.error};
  }
`

export const OrderedList = styled.ol`
  text-align: left;
  padding-left: ${({ theme }) => theme.spacing.LG}px;
`

export const RequirementsList = styled(BulletedList)`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  margin-top: ${({ theme }) => theme.spacing.SM}px;
`

export const CaptionText = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`

export const CenteredBlock = styled.div`
  text-align: center;
`

export const ErrorWrapper = styled.div`
  max-width: 480px;
  margin: 0 auto;
  width: 100%;
`

export const ActionButton = PrimitiveActionButton
