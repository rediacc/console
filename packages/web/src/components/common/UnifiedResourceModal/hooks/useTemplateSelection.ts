import { useState } from 'react';

interface UseTemplateSelectionReturn {
  selectedTemplate: string | null;
  setSelectedTemplate: (template: string | null) => void;
  showTemplateDetails: boolean;
  setShowTemplateDetails: (show: boolean) => void;
  templateToView: string | null;
  setTemplateToView: (template: string | null) => void;
}

interface UseTemplateSelectionProps {
  existingData?: Record<string, unknown>;
}

const resolvePreselectedTemplate = (existingData?: Record<string, unknown>): string | null => {
  if (
    existingData &&
    typeof (existingData as Record<string, unknown>).preselectedTemplate === 'string'
  ) {
    return (existingData as Record<string, string>).preselectedTemplate || null;
  }
  return null;
};

export const useTemplateSelection = ({
  existingData,
}: UseTemplateSelectionProps): UseTemplateSelectionReturn => {
  // State for template selection (for repos)
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(
    resolvePreselectedTemplate(existingData)
  );
  const [showTemplateDetails, setShowTemplateDetails] = useState(false);
  const [templateToView, setTemplateToView] = useState<string | null>(null);

  return {
    selectedTemplate,
    setSelectedTemplate,
    showTemplateDetails,
    setShowTemplateDetails,
    templateToView,
    setTemplateToView,
  };
};
