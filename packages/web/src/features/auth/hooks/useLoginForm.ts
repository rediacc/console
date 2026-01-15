import { Form } from 'antd';
import type { FormInstance } from 'antd/es/form';
import type { LoginFormValues } from '../types';

interface LoginFormState {
  form: FormInstance<LoginFormValues>;
  twoFAForm: FormInstance;
}

export const useLoginForm = (): LoginFormState => {
  const [form] = Form.useForm<LoginFormValues>();
  const [twoFAForm] = Form.useForm();

  return { form, twoFAForm };
};
