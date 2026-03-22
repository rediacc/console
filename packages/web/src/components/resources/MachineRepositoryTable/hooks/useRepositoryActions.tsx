import { DEFAULTS } from '@rediacc/shared/config';
import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import { Alert, Flex, Input, Typography } from 'antd';
import { preparePromotion } from '@/platform';
import { showMessage } from '@/utils/messages';
import type { Repository } from '../types';
import { getAxiosErrorMessage } from '../utils';

interface UseRepositoryActionsProps {
  teamName: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  teamRepositories: any[];
  confirm: (config: {
    title: string;
    content: React.ReactNode;
    okText: string;
    okType?: 'primary' | 'danger';
    cancelText: string;
    onOk: () => Promise<void>;
  }) => void;
  modal: {
    confirm: (config: {
      title: string;
      content: React.ReactNode;
      okText: string;
      cancelText: string;
      onOk: () => Promise<void>;
    }) => void;
  };
  promoteRepoMutation: {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mutateAsync: (params: { teamName: string; repositoryName: string }) => Promise<any>;
  };
  updateRepoNameMutation: {
    mutateAsync: (params: {
      teamName: string;
      currentRepositoryName: string;
      newRepositoryName: string;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    }) => Promise<any>;
  };
  updateRepoTagMutation: {
    mutateAsync: (params: {
      teamName: string;
      repositoryName: string;
      currentTag: string;
      newTag: string;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    }) => Promise<any>;
  };
  onActionComplete?: () => void;
  t: TypedTFunction;
}

export function useRepositoryActions({
  teamName,
  teamRepositories,
  confirm,
  modal,
  promoteRepoMutation,
  updateRepoNameMutation,
  updateRepoTagMutation,
  onActionComplete,
  t,
}: UseRepositoryActionsProps) {
  const handlePromoteToGrand = (repository: Repository) => {
    const context = preparePromotion(repository.name, repository.repositoryTag, teamRepositories);

    if (context.status === 'error') {
      showMessage(
        'error',
        context.errorCode === 'NOT_FOUND'
          ? t('resources:repositories.notFound')
          : t('resources:repositories.alreadyOriginalRepository')
      );
      return;
    }

    const { siblingClones, currentGrandName } = context;

    confirm({
      title: t('resources:repositories.promoteToGrandTitle'),
      content: (
        <Flex vertical>
          <Typography.Paragraph>
            {t('resources:repositories.promoteToGrandMessage', {
              name: repository.name,
              grand: currentGrandName,
            })}
          </Typography.Paragraph>
          {siblingClones.length > 0 && (
            <>
              <Typography.Paragraph>
                {t('resources:repositories.promoteWillUpdateSiblings', {
                  count: siblingClones.length,
                })}
              </Typography.Paragraph>
              <ul>
                {siblingClones.map((clone) => (
                  <li key={clone.repositoryGuid}>{clone.repositoryName}</li>
                ))}
              </ul>
            </>
          )}
          <Alert message={t('resources:repositories.promoteWarning')} type="warning" />
        </Flex>
      ),
      okText: t('resources:repositories.promoteButton'),
      okType: 'primary',
      cancelText: t('common:cancel'),
      onOk: async () => {
        try {
          await promoteRepoMutation.mutateAsync({
            teamName,
            repositoryName: repository.name,
          });
          showMessage(
            'success',
            t('resources:repositories.promoteSuccess', { name: repository.name })
          );
        } catch (error: unknown) {
          const errorMessage = getAxiosErrorMessage(
            error,
            t('resources:repositories.promoteFailed')
          );
          showMessage('error', errorMessage);
        }
      },
    });
  };

  const handleRenameRepo = (repository: Repository) => {
    let newName = repository.name;

    modal.confirm({
      title: t('resources:repositories.renameTitle'),
      content: (
        <Flex vertical>
          <Typography.Paragraph>
            {t('resources:repositories.renameMessage', { name: repository.name })}
          </Typography.Paragraph>
          <Input
            defaultValue={repository.name}
            placeholder={t('resources:repositories.newRepoName')}
            onChange={(e) => {
              newName = e.target.value;
            }}
            onPressEnter={(e) => {
              e.preventDefault();
            }}
            autoFocus
            data-testid="repository-rename-input"
          />
        </Flex>
      ),
      okText: t('common:save'),
      cancelText: t('common:cancel'),
      onOk: async () => {
        const trimmedName = newName.trim();

        if (!trimmedName) {
          showMessage('error', t('resources:repositories.emptyNameError'));
          throw new Error(t('resources:repositories.emptyNameError'));
        }

        if (trimmedName === repository.name) {
          showMessage('info', t('resources:repositories.nameUnchanged'));
          throw new Error(t('resources:repositories.nameUnchanged'));
        }

        const existingRepo = teamRepositories.find((r) => r.repositoryName === trimmedName);
        if (existingRepo) {
          showMessage(
            'error',
            t('resources:repositories.nameAlreadyExists', { name: trimmedName })
          );
          throw new Error(t('resources:repositories.nameAlreadyExists', { name: trimmedName }));
        }

        try {
          await updateRepoNameMutation.mutateAsync({
            teamName,
            currentRepositoryName: repository.name,
            newRepositoryName: trimmedName,
          });
          showMessage(
            'success',
            t('resources:repositories.renameSuccess', {
              oldName: repository.name,
              newName: trimmedName,
            })
          );

          if (onActionComplete) {
            onActionComplete();
          }
        } catch (error: unknown) {
          const errorMessage = getAxiosErrorMessage(
            error,
            t('resources:repositories.renameFailed')
          );
          showMessage('error', errorMessage);
          throw error;
        }
      },
    });
  };

  const handleRenameTag = (repository: Repository) => {
    let newTag = repository.repositoryTag ?? DEFAULTS.REPOSITORY.TAG;

    modal.confirm({
      title: t('resources:repositories.renameTagTitle'),
      content: (
        <Flex vertical>
          <Typography.Paragraph>
            {t('resources:repositories.renameTagMessage', {
              name: repository.name,
              tag: repository.repositoryTag,
            })}
          </Typography.Paragraph>
          <Input
            defaultValue={repository.repositoryTag}
            placeholder={t('resources:repositories.newTagName')}
            onChange={(e) => {
              newTag = e.target.value;
            }}
            onPressEnter={(e) => {
              e.preventDefault();
            }}
            autoFocus
            data-testid="repository-rename-tag-input"
          />
        </Flex>
      ),
      okText: t('common:save'),
      cancelText: t('common:cancel'),
      onOk: async () => {
        const trimmedTag = newTag.trim();

        if (!trimmedTag) {
          showMessage('error', t('resources:repositories.emptyTagError'));
          throw new Error(t('resources:repositories.emptyTagError'));
        }

        if (trimmedTag === repository.repositoryTag) {
          showMessage('info', t('resources:repositories.tagUnchanged'));
          throw new Error(t('resources:repositories.tagUnchanged'));
        }

        const existingTag = teamRepositories.find(
          (r) => r.repositoryName === repository.name && r.repositoryTag === trimmedTag
        );
        if (existingTag) {
          showMessage('error', t('resources:repositories.tagAlreadyExists', { tag: trimmedTag }));
          throw new Error(t('resources:repositories.tagAlreadyExists', { tag: trimmedTag }));
        }

        try {
          await updateRepoTagMutation.mutateAsync({
            teamName,
            repositoryName: repository.name,
            currentTag: repository.repositoryTag ?? DEFAULTS.REPOSITORY.TAG,
            newTag: trimmedTag,
          });
          showMessage(
            'success',
            t('resources:repositories.renameTagSuccess', {
              name: repository.name,
              oldTag: repository.repositoryTag,
              newTag: trimmedTag,
            })
          );

          if (onActionComplete) {
            onActionComplete();
          }
        } catch (error: unknown) {
          const errorMessage = getAxiosErrorMessage(
            error,
            t('resources:repositories.renameTagFailed')
          );
          showMessage('error', errorMessage);
          throw error;
        }
      },
    });
  };

  return {
    handlePromoteToGrand,
    handleRenameRepo,
    handleRenameTag,
  };
}
