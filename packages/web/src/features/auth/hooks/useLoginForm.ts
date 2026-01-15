import { Form } from 'antd';
import type { LoginFormValues } from '../types';
import type { FormInstance } from 'antd/es/form';

interface LoginFormState {
  form: FormInstance<LoginFormValues>;
  twoFAForm: FormInstance;
}

export const useLoginForm = (): LoginFormState => {
  const [form] = Form.useForm<LoginFormValues>();
  const [twoFAForm] = Form.useForm();

  return { form, twoFAForm };
};
