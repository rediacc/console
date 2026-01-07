import { Button, Flex, Form, Input, Select } from 'antd';
import { FORM_LAYOUTS } from '@/config/formLayouts';
import type { FormFieldConfig, ResourceFormProps } from './types';

function ResourceForm({
  form,
  fields,
  onSubmit,
  submitText = 'Submit',
  cancelText = 'Cancel',
  onCancel,
  loading = false,
}: ResourceFormProps) {
  const renderField = (field: FormFieldConfig) => {
    switch (field.type) {
      case 'select':
        return (
          <Select
            placeholder={field.placeholder}
            options={field.options}
            disabled={field.disabled}
            allowClear
            showSearch
            filterOption={(input, option) =>
              (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
            }
            data-testid={`resource-form-field-${field.name}`}
            className="w-full"
          />
        );

      case 'password':
        return (
          <Input.Password
            placeholder={field.placeholder}
            disabled={field.disabled}
            autoComplete="off"
            data-testid={`resource-form-field-${field.name}`}
            className="w-full"
          />
        );

      default:
        return (
          <Input
            type={field.type === 'email' ? 'email' : 'text'}
            placeholder={field.placeholder}
            disabled={field.disabled}
            autoComplete="off"
            data-testid={`resource-form-field-${field.name}`}
            className="w-full"
          />
        );
    }
  };

  const handleFinish = async (values: Record<string, unknown>) => {
    await onSubmit(values);
  };

  return (
    <Form
      form={form}
      {...FORM_LAYOUTS.horizontal}
      onFinish={handleFinish}
      labelAlign="right"
      colon
      data-testid="resource-form"
      className="w-full"
    >
      {fields.map((field) => {
        if (field.hidden) return null;

        return (
          <Form.Item
            key={field.name}
            name={field.name}
            label={field.label}
            required={field.required}
            rules={field.rules}
          >
            {renderField(field)}
          </Form.Item>
        );
      })}

      <Form.Item
        wrapperCol={{
          offset: FORM_LAYOUTS.horizontal.labelCol.span,
          span: FORM_LAYOUTS.horizontal.wrapperCol.span,
        }}
      >
        <Flex justify="flex-end" className="w-full">
          {onCancel && (
            <Button onClick={onCancel} disabled={loading} data-testid="resource-form-cancel-button">
              {cancelText}
            </Button>
          )}
          <Button
            type="primary"
            htmlType="submit"
            loading={loading}
            data-testid="resource-form-submit-button"
          >
            {submitText}
          </Button>
        </Flex>
      </Form.Item>
    </Form>
  );
}

export default ResourceForm;
