import React, { startTransition, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Flex,
  Form,
  Input,
  Modal,
  Row,
  Select,
  Space,
  Tag,
  Typography,
} from 'antd';
import { useTranslation } from 'react-i18next';
import { useMachines } from '@/api/queries/machines';
import type { QueueFunction } from '@/api/queries/queue';
import { useRepositories } from '@/api/queries/repositories';
import { useStorage } from '@/api/queries/storage';
import TemplatePreviewModal from '@/components/common/TemplatePreviewModal';
import { useLocalizedFunctions } from '@/services/functionsService';
import { ModalSize } from '@/types/modal';
import FunctionParameterField from './components/FunctionParameterField';
import PrioritySelector from './components/PrioritySelector';
import { useFunctionParameters } from './hooks/useFunctionParameters';
import { useFunctionSelection } from './hooks/useFunctionSelection';
import { useFunctionSubmission } from './hooks/useFunctionSubmission';
import { usePriorityManagement } from './hooks/usePriorityManagement';

type FunctionParamValue = string | number | string[] | undefined;
type FunctionParams = Record<string, FunctionParamValue>;

const { Paragraph } = Typography;
const QUICK_TASK_NAMES = ['ping', 'hello', 'ssh_test', 'health_check'];

interface FunctionSelectionModalProps {
  open: boolean;
  onCancel: () => void;
  onSubmit: (functionData: {
    function: QueueFunction;
    params: FunctionParams;
    priority: number;
    description: string;
    selectedMachine?: string;
  }) => void;
  title?: string;
  subtitle?: React.ReactNode;
  allowedCategories?: string[];
  loading?: boolean;
  showMachineSelection?: boolean;
  teamName?: string;
  machines?: Array<{ value: string; label: string; bridgeName: string }>;
  hiddenParams?: string[];
  defaultParams?: FunctionParams;
  preselectedFunction?: string;
  initialParams?: FunctionParams;
  currentMachineName?: string;
  additionalContext?: {
    sourceRepo?: string;
    parentRepo?: string | null;
  };
}

const FunctionSelectionModal: React.FC<FunctionSelectionModalProps> = ({
  open,
  onCancel,
  onSubmit,
  title,
  subtitle,
  allowedCategories,
  loading = false,
  showMachineSelection = false,
  teamName,
  machines = [],
  hiddenParams = [],
  defaultParams = {},
  preselectedFunction,
  initialParams = {},
  currentMachineName,
  additionalContext,
}) => {
  const { t } = useTranslation(['functions', 'common', 'machines']);
  const { functions: rawLocalizedFunctions, categories } = useLocalizedFunctions();

  // Filter out null values from localizedFunctions to satisfy the type constraint
  const localizedFunctions = useMemo(() => {
    const filtered: Record<string, QueueFunction> = {};
    for (const [key, value] of Object.entries(rawLocalizedFunctions)) {
      if (value !== null) {
        filtered[key] = value as QueueFunction;
      }
    }
    return filtered;
  }, [rawLocalizedFunctions]);

  const [selectedFunction, setSelectedFunction] = useState<QueueFunction | null>(null);
  const [functionParams, setFunctionParams] = useState<FunctionParams>({});
  const [functionPriority, setFunctionPriority] = useState(4);
  const [functionDescription, setFunctionDescription] = useState('');
  const [functionSearchTerm, setFunctionSearchTerm] = useState('');
  const [selectedMachine, setSelectedMachine] = useState<string>('');
  const [selectedTemplates, setSelectedTemplates] = useState<string[]>([]);
  const [showTemplateDetails, setShowTemplateDetails] = useState(false);
  const [templateToView, setTemplateToView] = useState<string | null>(null);

  // Fetch repositories for the current team
  const { data: repositories } = useRepositories(teamName);

  // Fetch machines and storage for destination dropdown
  const { data: machinesData } = useMachines(teamName);
  const { data: storageData } = useStorage(teamName);

  // Use custom hooks
  const { initializeParams } = useFunctionParameters({
    initialParams,
    hiddenParams,
    currentMachineName,
  });

  const handleFunctionSelect = (func: QueueFunction, params: FunctionParams) => {
    setSelectedFunction(func);
    setFunctionParams(params);

    // Auto-select P1 for quick tasks
    const quickTasks = ['ping', 'hello', 'ssh_test', 'health_check'];
    if (
      quickTasks.includes(func.name) ||
      func.name.includes('test') ||
      func.name.includes('check')
    ) {
      setFunctionPriority(1);
    } else {
      setFunctionPriority(4);
    }
  };

  const { handleSelectFunction, functionsByCategory } = useFunctionSelection({
    localizedFunctions,
    allowedCategories,
    functionSearchTerm,
    onSelectFunction: handleFunctionSelect,
    initializeParams,
  });

  const { priorityLegendItems, getPriorityLabel } = usePriorityManagement();

  const { handleSubmit: performSubmit } = useFunctionSubmission({
    selectedFunction,
    functionParams,
    functionPriority,
    functionDescription,
    selectedMachine,
    selectedTemplates,
    showMachineSelection,
    hiddenParams,
    defaultParams,
    onSubmit,
  });

  // Handle preselected function
  const previousOpenRef = useRef(false);

  useEffect(() => {
    const wasPreviouslyOpen = previousOpenRef.current;

    if (open && !wasPreviouslyOpen) {
      const preselected = preselectedFunction ? localizedFunctions[preselectedFunction] : undefined;

      if (preselected) {
        const func = preselected as QueueFunction;
        startTransition(() => {
          setSelectedFunction(func);
          setFunctionParams(initializeParams(func));
        });
      }
    }

    previousOpenRef.current = open;
  }, [open, preselectedFunction, localizedFunctions, initializeParams]);

  // Check if all required parameters are filled
  const areRequiredParamsFilled = useMemo(() => {
    if (!selectedFunction) return false;

    return Object.entries(selectedFunction.params)
      .filter(([paramName]) => !hiddenParams.includes(paramName))
      .every(([paramName, paramInfo]) => {
        if (!paramInfo.required) return true;

        // For template-selector, check selectedTemplates state
        if (paramInfo.ui === 'template-selector') {
          return selectedTemplates.length > 0;
        }

        const paramValue = functionParams[paramName];

        // For size parameters, check the value part
        if (paramInfo.format === 'size' && paramInfo.units) {
          const valueParam = functionParams[`${paramName}_value`];
          return typeof valueParam === 'number' && valueParam > 0;
        }

        // For other parameters, check the main value
        return paramValue !== undefined && paramValue !== null && paramValue !== '';
      });
  }, [selectedFunction, functionParams, hiddenParams, selectedTemplates]);

  const handleSubmit = async () => {
    await performSubmit();

    // Reset form
    setSelectedFunction(null);
    setFunctionParams({} as FunctionParams);
    setFunctionPriority(4);
    setFunctionDescription('');
    setFunctionSearchTerm('');
    setSelectedMachine('');
    setSelectedTemplates([]);
  };

  const handleCancel = () => {
    // Reset form
    setSelectedFunction(null);
    setFunctionParams({} as FunctionParams);
    setFunctionPriority(4);
    setFunctionDescription('');
    setFunctionSearchTerm('');
    setSelectedMachine('');
    setSelectedTemplates([]);
    onCancel();
  };

  const handleParamChange = (paramName: string, value: FunctionParamValue) => {
    setFunctionParams((prev) => ({
      ...prev,
      [paramName]: value,
    }));
  };

  return (
    <>
      <Modal
        title={
          <Flex vertical>
            <Typography.Text>{title || t('functions:selectFunction')}</Typography.Text>
            {subtitle && (
              <Typography.Text style={{ color: 'var(--ant-color-text-secondary)', fontSize: 12 }}>
                {subtitle}
              </Typography.Text>
            )}
          </Flex>
        }
        open={open}
        onCancel={handleCancel}
        className={ModalSize.Large}
        footer={[
          <Button key="cancel" onClick={handleCancel} data-testid="function-modal-cancel">
            {t('common:actions.cancel')}
          </Button>,
          <Button
            key="submit"
            htmlType="submit"
            onClick={handleSubmit}
            disabled={
              !selectedFunction ||
              (showMachineSelection && !selectedMachine) ||
              !areRequiredParamsFilled
            }
            loading={loading}
            data-testid="function-modal-submit"
          >
            {t('common:actions.addToQueue')}
          </Button>,
        ]}
        data-testid="function-modal"
      >
        <Row gutter={24}>
          {!preselectedFunction && (
            <Col span={10}>
              <Card title={t('functions:availableFunctions')} size="small">
                <Input.Search
                  placeholder={t('functions:searchFunctions')}
                  value={functionSearchTerm}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                    setFunctionSearchTerm(e.target.value)
                  }
                  autoComplete="off"
                  data-testid="function-modal-search"
                />
                <Flex vertical>
                  {Object.entries(functionsByCategory).map(([category, funcs]) => (
                    <Flex
                      vertical
                      key={category}
                      data-testid={`function-modal-category-${category}`}
                    >
                      <Flex>
                        <Typography.Text strong>
                          {categories[category]?.name || category}
                        </Typography.Text>
                      </Flex>
                      {funcs.map((func) => {
                        const isQuickTask =
                          QUICK_TASK_NAMES.includes(func.name) ||
                          func.name.includes('test') ||
                          func.name.includes('check');

                        return (
                          <Flex
                            vertical
                            component="button"
                            key={func.name}
                            // @ts-expect-error - Flex component accepts button-specific props when component="button"
                            type="button"
                            onClick={() => handleSelectFunction(func)}
                            data-testid={`function-modal-item-${func.name}`}
                            style={{
                              width: '100%',
                              cursor: 'pointer',
                              textAlign: 'left',
                            }}
                          >
                            <Flex align="center" justify="space-between">
                              <Typography.Text strong>{func.name}</Typography.Text>
                              {isQuickTask && (
                                <Tag color="warning">⚡ {t('functions:quickTaskBadge')}</Tag>
                              )}
                            </Flex>
                            <Typography.Text type="secondary">{func.description}</Typography.Text>
                          </Flex>
                        );
                      })}
                    </Flex>
                  ))}
                </Flex>
              </Card>
            </Col>
          )}

          <Col span={preselectedFunction ? 24 : 14}>
            {selectedFunction ? (
              <Flex vertical gap={24} style={{ width: '100%' }}>
                <Card title={`${t('functions:configure')}: ${selectedFunction.name}`} size="small">
                  <Paragraph>{selectedFunction.description}</Paragraph>

                  <Form layout="horizontal" labelCol={{ span: 8 }} wrapperCol={{ span: 16 }}>
                    {/* Show additional info for push function */}
                    {selectedFunction.name === 'push' && functionParams.dest && (
                      <Flex
                        style={{
                          display: 'grid',
                          gridTemplateColumns:
                            functionParams.state === 'online' ? '1fr 0.8fr' : '1fr',
                        }}
                      >
                        <Alert
                          type="info"
                          showIcon
                          message="Push Operation Details"
                          description={
                            <Space direction="vertical" size="small">
                              <Flex>
                                <Typography.Text strong>Destination Filename: </Typography.Text>
                                <Typography.Text code>{functionParams.dest}</Typography.Text>
                              </Flex>
                              {additionalContext?.parentRepo && (
                                <Flex>
                                  <Typography.Text strong>Repository Lineage: </Typography.Text>
                                  <Space>
                                    <Tag color="processing">{additionalContext.parentRepo}</Tag>
                                    <Typography.Text type="secondary">→</Typography.Text>
                                    <Tag color="success">{additionalContext.sourceRepo}</Tag>
                                    <Typography.Text type="secondary">→</Typography.Text>
                                    <Tag color="default">{functionParams.dest}</Tag>
                                  </Space>
                                </Flex>
                              )}
                              {!additionalContext?.parentRepo && additionalContext?.sourceRepo && (
                                <Flex>
                                  <Typography.Text strong>Source Repository: </Typography.Text>
                                  <Tag color="success">{additionalContext.sourceRepo}</Tag>
                                  <Typography.Text type="secondary"> (Original)</Typography.Text>
                                </Flex>
                              )}
                              <Flex>
                                <Typography.Text type="secondary">
                                  {functionParams.state === 'online'
                                    ? 'The repository will be pushed in online state (mounted).'
                                    : 'The repository will be pushed in offline state (unmounted).'}
                                </Typography.Text>
                              </Flex>
                            </Space>
                          }
                        />
                        {functionParams.state === 'online' && (
                          <Alert
                            type="warning"
                            showIcon
                            message={t('functions:onlinePushWarningTitle')}
                            description={
                              <Space direction="vertical" size="small">
                                <Typography.Text type="secondary">
                                  {t('functions:onlinePushWarningMessage')}
                                </Typography.Text>
                                <Flex>
                                  <a
                                    href="https://docs.rediacc.com/concepts/repo-push-operations"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    style={{ fontSize: 12 }}
                                  >
                                    {t('functions:onlinePushLearnMore')}
                                  </a>
                                </Flex>
                              </Space>
                            }
                          />
                        )}
                      </Flex>
                    )}

                    {/* Machine Selection */}
                    {showMachineSelection && (
                      <Form.Item label={t('machines:machine')} required>
                        <Select
                          value={selectedMachine}
                          onChange={setSelectedMachine}
                          placeholder={t('machines:selectMachine')}
                          options={machines}
                          data-testid="function-modal-machine-select"
                        />
                      </Form.Item>
                    )}

                    {/* Function Parameters */}
                    {Object.entries(selectedFunction.params)
                      .filter(([paramName]) => !hiddenParams.includes(paramName))
                      .map(([paramName, paramInfo]) => (
                        <Form.Item
                          key={paramName}
                          label={
                            paramInfo.help ? (
                              <Space size={4}>
                                <Typography.Text>{paramInfo.label || paramName}</Typography.Text>
                                {/* Help tooltip removed - handled in FunctionParameterField if needed */}
                              </Space>
                            ) : (
                              <Typography.Text>{paramInfo.label || paramName}</Typography.Text>
                            )
                          }
                          required={paramInfo.required}
                          {...(paramInfo.ui === 'template-selector'
                            ? { wrapperCol: { span: 24 }, labelCol: { span: 0 } }
                            : {})}
                        >
                          <FunctionParameterField
                            paramName={paramName}
                            paramInfo={paramInfo}
                            functionParams={functionParams}
                            selectedFunction={selectedFunction}
                            onParamChange={handleParamChange}
                            onTemplatesChange={setSelectedTemplates}
                            onTemplateView={(templateName) => {
                              setTemplateToView(templateName);
                              setShowTemplateDetails(true);
                            }}
                            selectedTemplates={selectedTemplates}
                            repositories={repositories}
                            machinesData={machinesData}
                            storageData={storageData}
                            currentMachineName={currentMachineName}
                          />
                        </Form.Item>
                      ))}

                    {/* Priority - Hidden when function is preselected */}
                    {!preselectedFunction && (
                      <PrioritySelector
                        priority={functionPriority}
                        onPriorityChange={setFunctionPriority}
                        priorityLegendItems={priorityLegendItems}
                        getPriorityLabel={getPriorityLabel}
                      />
                    )}
                  </Form>
                </Card>
              </Flex>
            ) : (
              <Card>
                <Empty description={t('functions:selectFunctionToConfigure')} />
              </Card>
            )}
          </Col>
        </Row>
      </Modal>

      {/* Template Preview Modal */}
      <TemplatePreviewModal
        open={showTemplateDetails}
        template={null}
        templateName={templateToView}
        onClose={() => {
          setShowTemplateDetails(false);
          setTemplateToView(null);
        }}
        onUseTemplate={(templateName) => {
          const templateId = typeof templateName === 'string' ? templateName : templateName.name;
          // Add to selection if not already selected
          if (!selectedTemplates.includes(templateId)) {
            setSelectedTemplates([...selectedTemplates, templateId]);
          }
          setShowTemplateDetails(false);
          setTemplateToView(null);
        }}
        context="repository-creation"
      />
    </>
  );
};

export default FunctionSelectionModal;
