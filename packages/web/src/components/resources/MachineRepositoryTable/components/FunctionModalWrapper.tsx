import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type { GetTeamRepositories_ResultSet1 } from '@rediacc/shared/types';
import { Flex, Space, Tag, Typography } from 'antd';
import React from 'react';
import FunctionSelectionModal from '@/components/common/FunctionSelectionModal';
import type { Machine } from '@/types';
import type { FunctionData } from '../hooks/useFunctionExecution';
import type { Repository } from '../types';

interface FunctionModalWrapperProps {
  isOpen: boolean;
  onCancel: () => void;
  onSubmit: (functionData: FunctionData) => Promise<void>;
  selectedRepository: Repository | null;
  selectedFunction: string | null;
  machine: Machine;
  teamRepositories: GetTeamRepositories_ResultSet1[];
  isExecuting: boolean;
  t: TypedTFunction;
}

export const FunctionModalWrapper: React.FC<FunctionModalWrapperProps> = ({
  isOpen,
  onCancel,
  onSubmit,
  selectedRepository,
  selectedFunction,
  machine,
  teamRepositories,
  isExecuting,
  t,
}) => {
  const getDefaultParams = () => {
    if (!selectedRepository) return {};
    const repository = teamRepositories.find(
      (r) =>
        r.repositoryName === selectedRepository.name &&
        r.repositoryTag === selectedRepository.repositoryTag
    );

    const repoParams = {
      repository: repository?.repositoryGuid ?? '',
      grand: repository?.grandGuid ?? '',
    };

    const stateParam =
      selectedFunction === 'backup_create' ||
      selectedFunction === 'backup_push' ||
      selectedFunction === 'backup_deploy' ||
      selectedFunction === 'fork'
        ? { state: selectedRepository.mounted ? 'online' : 'offline' }
        : {};

    return { ...repoParams, ...stateParam };
  };

  const getInitialParams = () => {
    if (
      (selectedFunction === 'fork' || selectedFunction === 'backup_deploy') &&
      selectedRepository
    ) {
      return { tag: new Date().toISOString().slice(0, 19).replace('T', '-').replaceAll(':', '-') };
    }
    return {};
  };

  const getAdditionalContext = () => {
    if (selectedFunction === 'backup_push' && selectedRepository) {
      const currentRepoData = teamRepositories.find(
        (r) =>
          r.repositoryName === selectedRepository.name &&
          r.repositoryTag === selectedRepository.repositoryTag
      );
      if (currentRepoData?.parentGuid) {
        const parentRepo = teamRepositories.find(
          (r) => r.repositoryGuid === currentRepoData.parentGuid
        );
        return {
          sourceRepo: selectedRepository.name,
          parentRepo: parentRepo?.repositoryName ?? null,
        };
      }
      return { sourceRepo: selectedRepository.name, parentRepo: null };
    }
    return undefined;
  };

  const renderSubtitle = () => {
    if (!selectedRepository) return undefined;

    return (
      <Flex vertical className="w-full gap-sm">
        <Space>
          <Typography.Text>{t('resources:repositories.Repository')}:</Typography.Text>
          <Tag>{selectedRepository.name}</Tag>
          <Typography.Text>•</Typography.Text>
          <Typography.Text>{t('machines:machine')}:</Typography.Text>
          <Tag>{machine.machineName}</Tag>
        </Space>
        {selectedFunction === 'backup_push' &&
          (() => {
            const currentRepoData = teamRepositories.find(
              (r) =>
                r.repositoryName === selectedRepository.name &&
                r.repositoryTag === selectedRepository.repositoryTag
            );
            if (currentRepoData?.parentGuid) {
              const parentRepo = teamRepositories.find(
                (r) => r.repositoryGuid === currentRepoData.parentGuid
              );
              if (parentRepo) {
                return (
                  <Space>
                    {/* eslint-disable-next-line no-restricted-syntax */}
                    <Typography.Text style={{ fontSize: 12 }}>
                      {t('resources:repositories.parentRepo')}:
                    </Typography.Text>
                    <Tag>{parentRepo.repositoryName}</Tag>
                    {/* eslint-disable-next-line no-restricted-syntax */}
                    <Typography.Text style={{ fontSize: 12 }}>→</Typography.Text>
                    {/* eslint-disable-next-line no-restricted-syntax */}
                    <Typography.Text style={{ fontSize: 12 }}>
                      {t('common:current')}:
                    </Typography.Text>
                    <Tag>{selectedRepository.name}</Tag>
                  </Space>
                );
              }
            }
            return null;
          })()}
      </Flex>
    );
  };

  return (
    <FunctionSelectionModal
      open={isOpen}
      onCancel={onCancel}
      onSubmit={onSubmit}
      title={t('machines:runFunction')}
      data-testid="machine-repo-list-function-modal"
      subtitle={renderSubtitle()}
      allowedCategories={['Repository', 'backup', 'network']}
      loading={isExecuting}
      showMachineSelection={false}
      teamName={machine.teamName ?? undefined}
      hiddenParams={['repository', 'grand', 'state']}
      defaultParams={getDefaultParams()}
      initialParams={getInitialParams()}
      preselectedFunction={selectedFunction ?? undefined}
      currentMachineName={machine.machineName ?? undefined}
      additionalContext={getAdditionalContext()}
    />
  );
};
