import styled from 'styled-components'
import { Radio, Button, Space } from 'antd'

export const PopoverContainer = styled.div`
  width: 400px;
`

export const OptionLabel = styled.label`
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  display: block;
  margin-bottom: ${({ theme }) => theme.spacing.XS}px;
  color: ${({ theme }) => theme.colors.textPrimary};
`

export const OptionGroup = styled(Radio.Group)`
  && {
    display: block;
    margin-top: ${({ theme }) => theme.spacing.XS}px;
  }
`

export const OptionRadio = styled(Radio)`
  && {
    display: block;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
    margin-bottom: ${({ theme }) => theme.spacing.XS}px;
  }
`

export const GeneratedValueCard = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.SM}px;
`

export const ValueHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: ${({ theme }) => theme.spacing.XS}px 0;
  color: ${({ theme }) => theme.colors.textPrimary};
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
`

export const ValueActions = styled.div`
  display: flex;
  gap: ${({ theme }) => theme.spacing.XS}px;
`

export const ValueContent = styled.div`
  word-break: break-all;
  max-height: 100px;
  overflow: auto;
  padding: ${({ theme }) => theme.spacing.SM}px;
  background: ${({ theme }) => theme.colors.bgPrimary};
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  border-radius: ${({ theme }) => theme.borderRadius.MD}px;
  font-size: ${({ theme }) => theme.fontSize.XS}px;
  line-height: ${({ theme }) => theme.lineHeight.NORMAL};
`

export const ActionRow = styled(Space)`
  && {
    margin-top: ${({ theme }) => theme.spacing.MD}px;
    width: 100%;
    justify-content: flex-end;
  }
`

export const ControlButton = styled(Button)`
  && {
    min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT}px;
    border-radius: ${({ theme }) => theme.borderRadius.LG}px;
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`

export const GeneratorButton = styled(Button)`
  && {
    color: ${({ theme }) => theme.colors.primary};
    min-height: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_SM}px;
    min-width: ${({ theme }) => theme.dimensions.CONTROL_HEIGHT_SM}px;
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  }
`

export const TitleStack = styled(Space)`
  && {
    gap: ${({ theme }) => theme.spacing.SM}px;
    align-items: center;
  }
`

export const CopyButton = styled(Button)`
  && {
    border-radius: ${({ theme }) => theme.borderRadius.SM}px;
    font-size: ${({ theme }) => theme.fontSize.XS}px;
  }
`

export const OptionsStack = styled(Space)`
  && {
    width: 100%;
  }
`
