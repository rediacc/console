import type { QueueFunction } from '@rediacc/shared/types';
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Flex,
  Form,
  Input,
  Row,
  Select,
  Space,
  Tag,
  Typography,
} from 'antd';
import React, { startTransition, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  useGetTeamMachines,
  useGetTeamRepositories,
  useGetTeamStorages,
} from '@/api/api-hooks.generated';
import { SizedModal } from '@/components/common/SizedModal';
import TemplatePreviewModal from '@/components/common/TemplatePreviewModal';
import { FORM_LAYOUTS } from '@/config/formLayouts';
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
const QUICK_TASK_NAMES = [
  'machine_ping',
  'machine_version',
  'machine_ssh_test',
  'health_check',
] as const;

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
  machines?: { value: string; label: string; bridgeName: string }[];
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
  const { data: repositories } = useGetTeamRepositories(teamName);

  // Fetch machines and storage for destination dropdown
  const { data: machinesData } = useGetTeamMachines(teamName);
  const { data: storageData } = useGetTeamStorages(teamName);

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
    const isQuickTask =
      (QUICK_TASK_NAMES as readonly string[]).includes(func.name) ||
      func.name.includes('test') ||
      func.name.includes('check');
    setFunctionPriority(isQuickTask ? 1 : 4);
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
        const func = preselected;
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
        return paramValue !== undefined && paramValue !== '';
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
      <SizedModal
        title={
          <Flex vertical>
            <Typography.Text>{title ?? t('functions:selectFunction')}</Typography.Text>
            {subtitle && <Typography.Text>{subtitle}</Typography.Text>}
          </Flex>
        }
        open={open}
        onCancel={handleCancel}
        size={ModalSize.Large}
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
                          {categories[category].name || category}
                        </Typography.Text>
                      </Flex>
                      {funcs.map((func) => {
                        const isQuickTask =
                          (QUICK_TASK_NAMES as readonly string[]).includes(func.name) ||
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
                            className="w-full cursor-pointer"
                          >
                            <Flex align="center" justify="space-between">
                              <Typography.Text strong>{func.name}</Typography.Text>
                              {isQuickTask && <Tag>⚡ {t('functions:quickTaskBadge')}</Tag>}
                            </Flex>
                            <Typography.Text>{func.description}</Typography.Text>
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
              <Flex vertical className="w-full">
                <Card title={`${t('functions:configure')}: ${selectedFunction.name}`} size="small">
                  <Paragraph>{selectedFunction.description}</Paragraph>

                  <Form {...FORM_LAYOUTS.horizontal}>
                    {/* Show additional info for push function */}
                    {selectedFunction.name === 'backup_push' && functionParams.dest && (
                      <Flex
                        // eslint-disable-next-line no-restricted-syntax
                        style={{
                          display: 'grid',
                          gridTemplateColumns:
                            functionParams.state === 'online' ? '1fr 0.8fr' : '1fr',
                        }}
                      >
                        <Alert
                          type="info"
                          message={t('functions:pushOperationDetails')}
                          description={
                            <Space direction="vertical" size="small">
                              <Flex>
                                <Typography.Text strong>
                                  {t('functions:destinationFilename')}:{' '}
                                </Typography.Text>
                                <Typography.Text code>{functionParams.dest}</Typography.Text>
                              </Flex>
                              {additionalContext?.parentRepo && (
                                <Flex>
                                  <Typography.Text strong>
                                    {t('functions:repositoryLineage')}:{' '}
                                  </Typography.Text>
                                  <Space>
                                    <Tag>{additionalContext.parentRepo}</Tag>
                                    <Typography.Text>→</Typography.Text>
                                    <Tag>{additionalContext.sourceRepo}</Tag>
                                    <Typography.Text>→</Typography.Text>
                                    <Tag>{functionParams.dest}</Tag>
                                  </Space>
                                </Flex>
                              )}
                              {!additionalContext?.parentRepo && additionalContext?.sourceRepo && (
                                <Flex>
                                  <Typography.Text strong>
                                    {t('functions:sourceRepository')}:{' '}
                                  </Typography.Text>
                                  <Tag>{additionalContext.sourceRepo}</Tag>
                                  <Typography.Text>{t('functions:original')}</Typography.Text>
                                </Flex>
                              )}
                              <Flex>
                                <Typography.Text>
                                  {functionParams.state === 'online'
                                    ? t('functions:repositoryWillBePushedOnline')
                                    : t('functions:repositoryWillBePushedOffline')}
                                </Typography.Text>
                              </Flex>
                            </Space>
                          }
                        />
                        {functionParams.state === 'online' && (
                          <Alert
                            type="warning"
                            message={t('functions:onlinePushWarningTitle')}
                            description={
                              <Space direction="vertical" size="small">
                                <Typography.Text>
                                  {t('functions:onlinePushWarningMessage')}
                                </Typography.Text>
                                <Flex>
                                  <a
                                    href="https://docs.rediacc.com/concepts/repo-push-operations"
                                    target="_blank"
                                    rel="noopener noreferrer"
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
                                <Typography.Text>{paramInfo.label ?? paramName}</Typography.Text>
                                {/* Help tooltip removed - handled in FunctionParameterField if needed */}
                              </Space>
                            ) : (
                              <Typography.Text>{paramInfo.label ?? paramName}</Typography.Text>
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
      </SizedModal>

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
      />
    </>
  );
};

export default FunctionSelectionModal;
