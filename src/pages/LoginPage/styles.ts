import styled from 'styled-components'
import { Card, Button, Input, Alert } from 'antd'

export const LoginCard = styled(Card)`
  width: ${({ theme }) => theme.dimensions.CARD_WIDTH_LG}px;
  backdrop-filter: blur(8px);
  background: ${({ theme }) => theme.colors.bgPrimary};
  border: 1px solid ${({ theme }) => theme.colors.borderSecondary};
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  box-shadow: ${({ theme }) => theme.shadows.CARD};
  padding: ${({ theme }) => theme.spacing['3']}px;
  
  .ant-card-body {
    padding: 0;
  }
  
  /* Mobile responsive */
  @media (max-width: 768px) {
    width: 100%;
    max-width: 100%;
    min-height: 100vh;
    border-radius: 0;
    border: none;
    box-shadow: none;
    display: flex;
    flex-direction: column;
    justify-content: center;
  }
  
  @media (max-width: 480px) {
    padding: ${({ theme }) => theme.spacing['2']}px;
  }
`

export const LoginContainer = styled.div`
  width: 100%;
`

export const LanguageSelectorWrapper = styled.div`
  display: flex;
  justify-content: flex-end;
  margin-bottom: -${({ theme }) => theme.spacing.SM}px;
  
  @media (max-width: 768px) {
    padding-right: 0;
    margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  }
`

export const LogoContainer = styled.div`
  display: flex;
  justify-content: center;
  align-items: center;
  height: ${({ theme }) => theme.spacing.XXXXXL}px;
  margin-top: -${({ theme }) => theme.spacing.SM}px;
  
  img {
    height: ${({ theme }) => theme.spacing.XL}px;
    width: auto;
    max-width: 150px;
    object-fit: contain;
  }
  
  @media (max-width: 768px) {
    margin-top: ${({ theme }) => theme.spacing.MD}px;
    margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  }
`

export const StyledAlert = styled(Alert)`
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  border: 2px solid ${({ theme }) => theme.colors.error};
  background-color: ${({ theme }) => theme.colors.bgError};
  padding: ${({ theme }) => theme.spacing.MD}px;
  box-shadow: ${({ theme }) => theme.shadows.ERROR_FIELD};
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
`

export const FormLabel = styled.label`
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  color: ${({ theme }) => theme.colors.textPrimary};
  margin-bottom: ${({ theme }) => theme.spacing.SM}px;
  display: block;
`

export const MasterPasswordLabel = styled(FormLabel)`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
  
  .anticon {
    color: ${({ theme }) => theme.colors.textTertiary};
  }
`

export const MasterPasswordFormItem = styled.div`
  animation: fadeIn 0.3s ease-out;
  
  @keyframes fadeIn {
    from {
      opacity: 0;
      transform: translateY(-10px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }
`

export const AdvancedOptionsContainer = styled.div`
  text-align: center;
  margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  margin-top: ${({ theme }) => theme.spacing.SM}px;
`

export const AdvancedOptionsButton = styled(Button)`
  color: ${({ theme }) => theme.colors.textTertiary};
  font-size: ${({ theme }) => theme.fontSize.SM}px;
  height: auto;
  padding: ${({ theme }) => theme.spacing.XS}px ${({ theme }) => theme.spacing.SM}px;
  border-radius: ${({ theme }) => theme.borderRadius.MD}px;
  transition: ${({ theme }) => theme.transitions.DEFAULT};
  
  &:hover {
    background-color: ${({ theme }) => theme.colors.bgHover};
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`

export const LoginButton = styled(Button)`
  background: ${({ theme }) => theme.colors.primary};
  border-color: ${({ theme }) => theme.colors.primary};
  height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT_LG}px;
  font-size: ${({ theme }) => theme.fontSize.BASE}px;
  font-weight: ${({ theme }) => theme.fontWeight.SEMIBOLD};
  box-shadow: ${({ theme }) => theme.shadows.BUTTON_DEFAULT};
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  
  &:hover:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: ${({ theme }) => theme.shadows.BUTTON_HOVER};
    background: ${({ theme }) => theme.colors.primaryHover};
    border-color: ${({ theme }) => theme.colors.primaryHover};
  }
  
  &:active:not(:disabled) {
    transform: translateY(0);
  }
  
  @media (max-width: 480px) {
    height: 48px;
    font-size: 16px;
  }
`

export const RegisterContainer = styled.div`
  text-align: center;
  margin-top: ${({ theme }) => theme.spacing.SM}px;
  
  .ant-typography {
    font-size: ${({ theme }) => theme.fontSize.SM}px;
  }
`

export const RegisterLink = styled.a`
  color: ${({ theme }) => theme.colors.primary};
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  text-decoration: none;
  border-radius: ${({ theme }) => theme.borderRadius.SM}px;
  padding: 4px 8px;
  margin-left: 4px; /* Add left margin for spacing */
  transition: ${({ theme }) => theme.transitions.DEFAULT};
  cursor: pointer;
  display: inline-block;
  
  &:hover {
    background-color: ${({ theme }) => theme.colors.primaryBg};
    color: ${({ theme }) => theme.colors.primary};
  }
  
  &:focus-visible {
    outline: 2px solid ${({ theme }) => theme.colors.primary};
    outline-offset: 2px;
    background-color: ${({ theme }) => theme.colors.primaryBg};
  }
`

export const SelectorsContainer = styled.div`
  text-align: center;
  margin-top: ${({ theme }) => theme.spacing.LG}px;
  
  > div:first-child {
    margin-bottom: ${({ theme }) => theme.spacing.XS}px;
  }
  
  /* Endpoint selector styling */
  [data-testid="endpoint-selector"] .ant-select-selector {
    padding: 4px 8px !important;
    min-height: 32px !important;
    display: flex !important;
    align-items: center !important;
    
    /* Fix icon alignment */
    .ant-select-selection-item {
      display: flex !important;
      align-items: center !important;
      line-height: 1.5 !important;
    }
    
    /* Suffix icon alignment */
    .ant-select-arrow {
      display: flex !important;
      align-items: center !important;
      height: 100% !important;
      
      .anticon {
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
      }
    }
  }

  /* Version selector button styling */
  [data-testid="version-selector"] {
    padding: 4px 12px !important;
    min-height: 32px !important;
    display: inline-flex !important;
    align-items: center !important;
    gap: 6px !important;
    
    /* Fix icon padding inside button */
    .anticon {
      display: flex !important;
      align-items: center !important;
      justify-content: center !important;
      margin: 0 !important;
      padding: 0 !important;
      line-height: 1 !important;
      vertical-align: middle !important;
    }
    
    /* Ensure text and icon are vertically centered */
    > * {
      display: flex !important;
      align-items: center !important;
    }
    
    /* Fix button content alignment */
    &.ant-btn {
      display: inline-flex !important;
      align-items: center !important;
      justify-content: center !important;
      
      .ant-btn-icon {
        display: flex !important;
        align-items: center !important;
        line-height: 1 !important;
      }
    }
  }
  
  @media (max-width: 768px) {
    margin-top: ${({ theme }) => theme.spacing.XL}px;
    margin-bottom: ${({ theme }) => theme.spacing.MD}px;
  }
`

export const TFAModalTitle = styled.div`
  display: flex;
  align-items: center;
  gap: ${({ theme }) => theme.spacing.SM}px;
  
  .anticon {
    color: ${({ theme }) => theme.colors.primary};
  }
`

export const TFACodeInput = styled(Input)`
  text-align: center;
  font-size: ${({ theme }) => theme.fontSize.XL}px;
  letter-spacing: ${({ theme }) => theme.spacing.SM}px;
`

export const TFAButtonContainer = styled.div`
  display: flex;
  justify-content: flex-end;
  gap: ${({ theme }) => theme.spacing.SM}px;
  width: 100%;
`

export const TFAVerifyButton = styled(Button)`
  background: ${({ theme }) => theme.colors.primary};
  border-color: ${({ theme }) => theme.colors.primary};
  min-height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT}px;
  min-width: ${({ theme }) => theme.dimensions.INPUT_HEIGHT}px;
  
  &:hover:not(:disabled) {
    background: ${({ theme }) => theme.colors.primaryHover};
    border-color: ${({ theme }) => theme.colors.primaryHover};
  }
`

// Styled Input components for better icon styling
export const StyledInput = styled(Input)`
  height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT_LG}px;
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  font-size: ${({ theme }) => theme.fontSize.BASE}px;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden; /* Prevent inner input from covering focus border */
  
  /* Remove default padding - will be added by prefix/suffix */
  &.ant-input-affix-wrapper {
    padding: 0;
  }
  
  /* Input element inside wrapper - only horizontal padding */
  input.ant-input {
    padding: 0 14px;
    height: 100%;
  }
  
  .ant-input-prefix {
    margin-left: 14px;
    margin-right: ${({ theme }) => theme.spacing.SM}px;
    color: ${({ theme }) => theme.colors.textTertiary};
    font-size: ${({ theme }) => theme.fontSize.LG}px;
    transition: color 0.2s ease;
    
    .anticon {
      display: flex;
      align-items: center;
      justify-content: center;
    }
  }
  
  .ant-input-suffix {
    margin-right: 14px;
  }
  
  &:hover .ant-input-prefix,
  &:focus .ant-input-prefix,
  &.ant-input-affix-wrapper-focused .ant-input-prefix {
    color: ${({ theme }) => theme.colors.primary};
  }
  
  /* Focus state - smaller shadow */
  &:focus,
  &.ant-input-affix-wrapper-focused {
    border-color: ${({ theme }) => theme.colors.primary};
    box-shadow: 0 0 0 1px ${({ theme }) => theme.colors.primary};
    outline: none;
  }
  
  /* Error state - smaller shadow */
  &.ant-input-status-error,
  &.ant-input-affix-wrapper-status-error {
    border-color: ${({ theme }) => theme.colors.error};
    box-shadow: 0 0 0 1px ${({ theme }) => theme.colors.error};
  }
  
  /* Autofill styles - override Chrome's yellow background */
  input:-webkit-autofill,
  input:-webkit-autofill:hover,
  input:-webkit-autofill:focus,
  input:-webkit-autofill:active {
    -webkit-box-shadow: 0 0 0 30px ${({ theme }) => theme.colors.bgPrimary} inset !important;
    -webkit-text-fill-color: ${({ theme }) => theme.colors.textPrimary} !important;
    transition: background-color 5000s ease-in-out 0s;
  }
  
  /* Mobile responsive */
  @media (max-width: 480px) {
    height: 48px;
    font-size: 16px; /* Prevent zoom on iOS */
    
    input.ant-input {
      font-size: 16px;
    }
  }
`

export const StyledPasswordInput = styled(Input.Password)`
  height: ${({ theme }) => theme.dimensions.INPUT_HEIGHT_LG}px;
  border-radius: ${({ theme }) => theme.borderRadius.LG}px;
  font-size: ${({ theme }) => theme.fontSize.BASE}px;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden; /* Prevent inner input from covering focus border */
  
  /* Remove default padding - will be added by prefix/suffix */
  &.ant-input-affix-wrapper {
    padding: 0;
  }
  
  /* Input element inside wrapper - only horizontal padding */
  input.ant-input {
    padding: 0 14px;
    height: 100%;
  }
  
  .ant-input-prefix {
    margin-left: 14px;
    margin-right: ${({ theme }) => theme.spacing.SM}px;
    color: ${({ theme }) => theme.colors.textTertiary};
    font-size: ${({ theme }) => theme.fontSize.LG}px;
    transition: color 0.2s ease;
    
    .anticon {
      display: flex;
      align-items: center;
      justify-content: center;
    }
  }
  
  .ant-input-suffix {
    margin-right: 14px;
    margin-left: ${({ theme }) => theme.spacing.SM}px;
    
    .ant-input-password-icon {
      color: ${({ theme }) => theme.colors.textTertiary};
      font-size: ${({ theme }) => theme.fontSize.LG}px;
      transition: ${({ theme }) => theme.transitions.DEFAULT};
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      padding: 4px;
      border-radius: 4px;
      
      &:hover {
        color: ${({ theme }) => theme.colors.textSecondary};
        background-color: ${({ theme }) => theme.colors.bgHover};
      }
      
      &:active {
        transform: scale(0.95);
      }
    }
  }
  
  &:hover .ant-input-prefix,
  &:focus .ant-input-prefix,
  &.ant-input-affix-wrapper-focused .ant-input-prefix {
    color: ${({ theme }) => theme.colors.primary};
  }
  
  /* Focus state - smaller shadow */
  &:focus,
  &.ant-input-affix-wrapper-focused {
    border-color: ${({ theme }) => theme.colors.primary};
    box-shadow: 0 0 0 1px ${({ theme }) => theme.colors.primary};
    outline: none;
  }
  
  /* Error state - smaller shadow */
  &.ant-input-status-error,
  &.ant-input-affix-wrapper-status-error {
    border-color: ${({ theme }) => theme.colors.error};
    box-shadow: 0 0 0 1px ${({ theme }) => theme.colors.error};
  }
  
  /* Autofill styles - override Chrome's yellow background */
  input:-webkit-autofill,
  input:-webkit-autofill:hover,
  input:-webkit-autofill:focus,
  input:-webkit-autofill:active {
    -webkit-box-shadow: 0 0 0 30px ${({ theme }) => theme.colors.bgPrimary} inset !important;
    -webkit-text-fill-color: ${({ theme }) => theme.colors.textPrimary} !important;
    transition: background-color 5000s ease-in-out 0s;
  }
  
  /* Mobile responsive */
  @media (max-width: 480px) {
    height: 48px;
    font-size: 16px; /* Prevent zoom on iOS */
    
    input.ant-input {
      font-size: 16px;
    }
  }
`
