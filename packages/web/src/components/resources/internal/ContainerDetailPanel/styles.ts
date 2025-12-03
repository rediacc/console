import styled from 'styled-components'
import { Button, Card, Divider, Typography } from 'antd'
import {
  PanelWrapper,
  StickyHeader,
  ContentWrapper,
  InlineField,
  LabelText,
  MonospaceValue,
  StrongValueText,
  ValueText,
} from '../detailPanelPrimitives'

const { Title, Text } = Typography

export const DetailPanel = styled(PanelWrapper)`
  .ant-card {
    background-color: ${({ theme }) => theme.colors.bgSecondary};
    border-color: ${({ theme }) => theme.colors.borderSecondary};
  }
`

export const Header = styled(StickyHeader)`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const HeaderTop = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const TitleGroup = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const PanelTitle = styled(Title).attrs({ level: 4 })`
  && {
    margin: 0;
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`

export const CollapseButton = styled(Button)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  }
`

export const TagGroup = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({ theme }) => theme.spacing.XS}px;
`

export const PanelContent = styled(ContentWrapper)`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.LG}px;
`

export const SectionHeader = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const SectionTitle = styled(Title).attrs({ level: 5 })`
  && {
    margin: 0;
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`

export const SectionCard = styled(Card).attrs({ size: 'small' })`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  }
`

export const FieldList = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const FieldRow = styled(InlineField)`
  gap: ${({ theme }) => theme.spacing.SM}px;
  align-items: baseline;
`

export const FieldLabel = styled(LabelText)`
  min-width: 160px;
`

export const FieldValue = styled(ValueText)`
  word-break: break-word;
`

export const FieldValueStrong = styled(StrongValueText)`
  word-break: break-word;
`

export const FieldValueMonospace = styled(MonospaceValue)`
  word-break: break-word;
`

export const SectionDivider = styled(Divider)`
  && {
    margin: ${({ theme }) => `${theme.spacing.LG}px 0`};
  }
`

export const DividerLabel = styled.span`
  display: inline-flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
`

export const MetricsGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: ${({ theme }) => theme.spacing.MD}px;
`

export const MetricCard = styled(Card).attrs({ size: 'small' })`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  }
`

export const MetricLabel = styled(Text)`
  && {
    color: ${({ theme }) => theme.colors.textSecondary};
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`

export const MetricValue = styled(Text)<{ $isWarning?: boolean }>`
  && {
    font-size: ${({ theme }) => theme.fontSize.LG}px;
    font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
    color: ${({ theme, $isWarning }) => ($isWarning ? theme.colors.error : theme.colors.textPrimary)};
  }
`

export const SectionStack = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const InlineText = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    color: ${({ theme }) => theme.colors.textPrimary};
  }
`

export const SubduedText = styled(Text)`
  && {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`
