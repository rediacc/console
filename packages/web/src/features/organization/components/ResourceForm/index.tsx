import { useCallback } from 'react';
import { Button, Flex, Form, Input, Select } from 'antd';
import { Controller, FieldValues } from 'react-hook-form';
import { FormFieldConfig, ResourceFormProps } from './types';

function ResourceForm<T extends FieldValues = FieldValues>({
  form,
  fields,
  onSubmit,
  submitText = 'Submit',
  cancelText = 'Cancel',
  onCancel,
  loading = false,
  layout = 'vertical',
}: ResourceFormProps<T>) {
  const {
    control,
    handleSubmit,
    formState: { errors },
  } = form;

  const renderField = (field: FormFieldConfig<T>) => {
    switch (field.type) {
      case 'select':
        return (
          <Controller
            name={field.name}
            control={control}
            render={({ field: controllerField }) => (
              <Select
                {...controllerField}
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
            )}
          />
        );

      case 'password':
        return (
          <Controller
            name={field.name}
            control={control}
            render={({ field: controllerField }) => (
              <Input.Password
                {...controllerField}
                placeholder={field.placeholder}
                disabled={field.disabled}
                autoComplete="off"
                data-testid={`resource-form-field-${field.name}`}
                className="w-full"
              />
            )}
          />
        );

      default:
        return (
          <Controller
            name={field.name}
            control={control}
            render={({ field: controllerField }) => (
              <Input
                {...controllerField}
                type={field.type === 'email' ? 'email' : 'text'}
                placeholder={field.placeholder}
                disabled={field.disabled}
                autoComplete="off"
                data-testid={`resource-form-field-${field.name}`}
                className="w-full"
              />
            )}
          />
        );
    }
  };

  const formLayout = layout === 'vertical' ? 'horizontal' : layout;
  const labelCol = { span: 6 };
  const wrapperCol = { span: 18 };

  const onFormFinish = useCallback(() => {
    void handleSubmit(onSubmit)();
  }, [handleSubmit, onSubmit]);

  return (
    <Form
      layout={formLayout}
      onFinish={onFormFinish}
      labelCol={labelCol}
      wrapperCol={wrapperCol}
      labelAlign="right"
      colon
      data-testid="resource-form"
      className="w-full"
    >
      {fields.map((field) => {
        if (field.hidden) return null;

        const error = errors[field.name as keyof typeof errors];

        return (
          <Form.Item
            key={field.name}
            label={field.label}
            required={field.required}
            validateStatus={error ? 'error' : undefined}
            help={error?.message as string}
          >
            {renderField(field)}
          </Form.Item>
        );
      })}

      <Form.Item wrapperCol={{ offset: labelCol.span, span: wrapperCol.span }}>
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
