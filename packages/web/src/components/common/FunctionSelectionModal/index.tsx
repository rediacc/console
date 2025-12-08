import React, { startTransition, useEffect, useMemo, useRef, useState } from 'react';
import { Col, Empty, Form, Row, Select, Space, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { useMachines } from '@/api/queries/machines';
import type { QueueFunction } from '@/api/queries/queue';
import { useRepos } from '@/api/queries/repos';
import { useStorage } from '@/api/queries/storage';
import TemplatePreviewModal from '@/components/common/TemplatePreviewModal';
import { RediaccButton, RediaccStack, RediaccText } from '@/components/ui';
import { useLocalizedFunctions } from '@/services/functionsService';
import { ModalHeader, ModalSubtitle, ModalTitle } from '@/styles/primitives';
import { ModalSize } from '@/types/modal';
import FunctionParameterField from './components/FunctionParameterField';
import PrioritySelector from './components/PrioritySelector';
import { useFunctionParameters } from './hooks/useFunctionParameters';
import { useFunctionSelection } from './hooks/useFunctionSelection';
import { useFunctionSubmission } from './hooks/useFunctionSubmission';
import { usePriorityManagement } from './hooks/usePriorityManagement';
import {
  AlertLink,
  AlertLinkWrapper,
  CategorySection,
  ConfigCard,
  FunctionItemHeader,
  FunctionList,
  FunctionListCard,
  FunctionOption,
  LineageSeparator,
  LineageTag,
  PushAlertCard,
  PushAlertsRow,
  QuickTaskTag,
  SearchInput,
  StyledModal,
} from './styles';

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
  const { functions: localizedFunctions, categories } = useLocalizedFunctions();

  const [selectedFunction, setSelectedFunction] = useState<QueueFunction | null>(null);
  const [functionParams, setFunctionParams] = useState<FunctionParams>({});
  const [functionPriority, setFunctionPriority] = useState(4);
  const [functionDescription, setFunctionDescription] = useState('');
  const [functionSearchTerm, setFunctionSearchTerm] = useState('');
  const [selectedMachine, setSelectedMachine] = useState<string>('');
  const [selectedTemplates, setSelectedTemplates] = useState<string[]>([]);
  const [showTemplateDetails, setShowTemplateDetails] = useState(false);
  const [templateToView, setTemplateToView] = useState<string | null>(null);

  // Fetch repos for the current team
  const { data: repos } = useRepos(teamName);

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
      <StyledModal
        title={
          <ModalHeader>
            <ModalTitle>
              <span>{title || t('functions:selectFunction')}</span>
              {subtitle && <ModalSubtitle as="div">{subtitle}</ModalSubtitle>}
            </ModalTitle>
          </ModalHeader>
        }
        open={open}
        onCancel={handleCancel}
        className={ModalSize.ExtraLarge}
        footer={[
          <RediaccButton key="cancel" onClick={handleCancel} data-testid="function-modal-cancel">
            {t('common:actions.cancel')}
          </RediaccButton>,
          <RediaccButton
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
          </RediaccButton>,
        ]}
        data-testid="function-modal"
      >
        <Row gutter={24}>
          {!preselectedFunction && (
            <Col span={10}>
              <FunctionListCard title={t('functions:availableFunctions')} size="sm">
                <SearchInput
                  placeholder={t('functions:searchFunctions')}
                  value={functionSearchTerm}
                  onChange={(e) => setFunctionSearchTerm(e.target.value)}
                  autoComplete="off"
                  data-testid="function-modal-search"
                />
                <FunctionList>
                  {Object.entries(functionsByCategory).map(([category, funcs]) => (
                    <CategorySection
                      key={category}
                      data-testid={`function-modal-category-${category}`}
                    >
                      <RediaccText variant="title" style={{ display: 'block', marginBottom: 8 }}>
                        {categories[category]?.name || category}
                      </RediaccText>
                      {funcs.map((func) => {
                        const isQuickTask =
                          QUICK_TASK_NAMES.includes(func.name) ||
                          func.name.includes('test') ||
                          func.name.includes('check');

                        return (
                          <FunctionOption
                            key={func.name}
                            onClick={() => handleSelectFunction(func)}
                            $selected={selectedFunction?.name === func.name}
                            data-testid={`function-modal-item-${func.name}`}
                          >
                            <FunctionItemHeader>
                              <RediaccText weight="bold">{func.name}</RediaccText>
                              {isQuickTask && (
                                <QuickTaskTag>⚡ {t('functions:quickTaskBadge')}</QuickTaskTag>
                              )}
                            </FunctionItemHeader>
                            <RediaccText variant="description">{func.description}</RediaccText>
                          </FunctionOption>
                        );
                      })}
                    </CategorySection>
                  ))}
                </FunctionList>
              </FunctionListCard>
            </Col>
          )}

          <Col span={preselectedFunction ? 24 : 14}>
            {selectedFunction ? (
              <RediaccStack variant="spaced-column" fullWidth>
                <ConfigCard
                  title={`${t('functions:configure')}: ${selectedFunction.name}`}
                  size="sm"
                >
                  <Paragraph>{selectedFunction.description}</Paragraph>

                  <Form layout="horizontal" labelCol={{ span: 8 }} wrapperCol={{ span: 16 }}>
                    {/* Show additional info for push function */}
                    {selectedFunction.name === 'push' && functionParams.dest && (
                      <PushAlertsRow $hasWarning={functionParams.state === 'online'}>
                        <PushAlertCard
                          $variant="info"
                          variant="info"
                          showIcon
                          message="Push Operation Details"
                          description={
                            <Space direction="vertical" size="small">
                              <div>
                                <RediaccText weight="bold">Destination Filename: </RediaccText>
                                <RediaccText code>{functionParams.dest}</RediaccText>
                              </div>
                              {additionalContext?.parentRepo && (
                                <div>
                                  <RediaccText weight="bold">Repo Lineage: </RediaccText>
                                  <Space>
                                    <LineageTag $variant="parent">
                                      {additionalContext.parentRepo}
                                    </LineageTag>
                                    <LineageSeparator>→</LineageSeparator>
                                    <LineageTag $variant="source">
                                      {additionalContext.sourceRepo}
                                    </LineageTag>
                                    <LineageSeparator>→</LineageSeparator>
                                    <LineageTag $variant="destination">
                                      {functionParams.dest}
                                    </LineageTag>
                                  </Space>
                                </div>
                              )}
                              {!additionalContext?.parentRepo && additionalContext?.sourceRepo && (
                                <div>
                                  <RediaccText weight="bold">Source Repo: </RediaccText>
                                  <LineageTag $variant="source">
                                    {additionalContext.sourceRepo}
                                  </LineageTag>
                                  <RediaccText variant="description" as="span">
                                    {' '}
                                    (Original)
                                  </RediaccText>
                                </div>
                              )}
                              <div>
                                <RediaccText variant="description">
                                  {functionParams.state === 'online'
                                    ? 'The repo will be pushed in online state (mounted).'
                                    : 'The repo will be pushed in offline state (unmounted).'}
                                </RediaccText>
                              </div>
                            </Space>
                          }
                        />
                        {functionParams.state === 'online' && (
                          <PushAlertCard
                            $variant="warning"
                            variant="warning"
                            showIcon
                            message={t('functions:onlinePushWarningTitle')}
                            description={
                              <Space direction="vertical" size="small">
                                <RediaccText variant="description">
                                  {t('functions:onlinePushWarningMessage')}
                                </RediaccText>
                                <AlertLinkWrapper>
                                  <AlertLink
                                    href="https://docs.rediacc.com/concepts/repo-push-operations"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                  >
                                    {t('functions:onlinePushLearnMore')}
                                  </AlertLink>
                                </AlertLinkWrapper>
                              </Space>
                            }
                          />
                        )}
                      </PushAlertsRow>
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
                                <span>{paramInfo.label || paramName}</span>
                                {/* Help tooltip removed - handled in FunctionParameterField if needed */}
                              </Space>
                            ) : (
                              <span>{paramInfo.label || paramName}</span>
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
                            repos={repos}
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
                </ConfigCard>
              </RediaccStack>
            ) : (
              <ConfigCard>
                <Empty description={t('functions:selectFunctionToConfigure')} />
              </ConfigCard>
            )}
          </Col>
        </Row>
      </StyledModal>

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
        context="repo-creation"
      />
    </>
  );
};

export default FunctionSelectionModal;
