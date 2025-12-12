import React from 'react';
import type { QueueFunction } from '@/api/queries/queue';
import FunctionSelectionModal from '@/components/common/FunctionSelectionModal';
import TemplatePreviewModal from '@/components/common/TemplatePreviewModal';
import VaultEditorModal from '@/components/common/VaultEditorModal';

type FunctionSubmitPayload = {
  function: QueueFunction;
  params: Record<string, string | number | string[] | undefined>;
  priority: number;
  description: string;
  selectedMachine?: string;
};

interface DialogState {
  isOpen: boolean;
  open: () => void;
  close: () => void;
}

interface ResourceModalDialogsProps {
  // Vault Editor props
  showVaultEditor: boolean;
  vaultModal: DialogState;
  entityType: string;
  vaultTitle: string;
  initialVault: string;
  initialVersion: number;
  isUpdatingVault: boolean;
  onVaultSave: (vault: string, version: number) => Promise<void>;
  onVaultCancel: () => void;

  // Function Selection Modal props
  showFunctionModal: boolean;
  functionModal: DialogState;
  functionTitle: string;
  functionSubtitle: React.ReactNode;
  functionCategories: string[];
  isSubmitting: boolean;
  showMachineSelection: boolean;
  teamName?: string;
  machines: Array<{ value: string; label: string; bridgeName: string }>;
  hiddenParams: string[];
  defaultParams: Record<string, string | number | string[] | undefined>;
  preselectedFunction?: string;
  onFunctionSubmit: (functionData: FunctionSubmitPayload) => Promise<void>;
  onFunctionCancel: () => void;

  // Template Preview Modal props
  showTemplatePreview: boolean;
  templateToView: string | null;
  onTemplateClose: () => void;
  onTemplateUse: (templateName: string | { name: string }) => void;
}

export const ResourceModalDialogs: React.FC<ResourceModalDialogsProps> = ({
  // Vault Editor
  showVaultEditor,
  vaultModal,
  entityType,
  vaultTitle,
  initialVault,
  initialVersion,
  isUpdatingVault,
  onVaultSave,
  onVaultCancel,

  // Function Selection
  showFunctionModal,
  functionModal,
  functionTitle,
  functionSubtitle,
  functionCategories,
  isSubmitting,
  showMachineSelection,
  teamName,
  machines,
  hiddenParams,
  defaultParams,
  preselectedFunction,
  onFunctionSubmit,
  onFunctionCancel,

  // Template Preview
  showTemplatePreview,
  templateToView,
  onTemplateClose,
  onTemplateUse,
}) => {
  return (
    <>
      {/* Vault Editor Modal */}
      {showVaultEditor && (
        <VaultEditorModal
          open={vaultModal.isOpen}
          onCancel={onVaultCancel}
          onSave={onVaultSave}
          entityType={entityType}
          title={vaultTitle}
          initialVault={initialVault}
          initialVersion={initialVersion}
          loading={isUpdatingVault}
        />
      )}

      {/* Function Selection Modal */}
      {showFunctionModal && (
        <FunctionSelectionModal
          open={functionModal.isOpen}
          onCancel={onFunctionCancel}
          onSubmit={onFunctionSubmit}
          title={functionTitle}
          subtitle={functionSubtitle}
          allowedCategories={functionCategories}
          loading={isSubmitting}
          showMachineSelection={showMachineSelection}
          teamName={teamName}
          machines={machines}
          hiddenParams={hiddenParams}
          defaultParams={defaultParams}
          preselectedFunction={preselectedFunction}
        />
      )}

      {/* Template Preview Modal */}
      <TemplatePreviewModal
        open={showTemplatePreview}
        template={null}
        templateName={templateToView}
        onClose={onTemplateClose}
        onUseTemplate={onTemplateUse}
        context="repository-creation"
      />
    </>
  );
};
