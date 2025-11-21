import styled from 'styled-components'
import { Form, Input, Select, Space } from 'antd'

export const StyledForm = styled(Form)`
  width: 100%;
`

export const TextInput = styled(Input)`
  && {
    width: 100%;
  }
`

export const PasswordInput = styled(Input.Password)`
  && {
    width: 100%;
  }
`

export const FieldSelect = styled(Select)`
  && {
    width: 100%;
  }
`

export const FormActions = styled(Form.Item)`
  margin-top: ${({ theme }) => theme.spacing.PAGE_CONTAINER}px;
  margin-bottom: 0;
`

export const ActionButtons = styled(Space)`
  width: 100%;
  justify-content: flex-end;
`
