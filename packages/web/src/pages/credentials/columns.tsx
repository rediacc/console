import { Space, Tag } from 'antd';
import type { Repository } from '@/api/queries/repositories';
import { ActionButtonGroup, type ActionButtonConfig } from '@/components/common/ActionButtonGroup';
import { createActionColumn } from '@/components/common/columns';
import { COLUMN_RESPONSIVE, COLUMN_WIDTHS } from '@/components/common/ResourceListView';
import { featureFlags } from '@/config/featureFlags';
import { DeleteOutlined, EditOutlined, HistoryOutlined, InboxOutlined } from '@/utils/optimizedIcons';
import type { ColumnsType } from 'antd/es/table';
import type { TFunction } from 'i18next';

interface BuildRepositoryColumnsParams {
  t: TFunction<'resources' | 'machines' | 'common'>;
  onEdit: (repository: Repository) => void;
  onTrace: (repository: Repository) => void;
  onDelete: (repository: Repository) => void;
}

export const buildRepositoryColumns = ({
  t,
  onEdit,
  onTrace,
  onDelete,
}: BuildRepositoryColumnsParams): ColumnsType<Repository> => [
  {
    title: t('repositories.repositoryName'),
    dataIndex: 'repositoryName',
    key: 'repositoryName',
    width: COLUMN_WIDTHS.NAME,
    ellipsis: true,
    render: (text: string) => (
      <Space>
        <InboxOutlined />
        <strong>{text}</strong>
      </Space>
    ),
  },
  {
    title: t('general.team'),
    dataIndex: 'teamName',
    key: 'teamName',
    width: COLUMN_WIDTHS.TAG,
    ellipsis: true,
    render: (teamName: string) => <Tag>{teamName}</Tag>,
  },
  ...(featureFlags.isEnabled('vaultVersionColumns')
    ? [
        {
          title: t('general.vaultVersion'),
          dataIndex: 'vaultVersion',
          key: 'vaultVersion',
          width: COLUMN_WIDTHS.VERSION,
          align: 'center' as const,
          responsive: COLUMN_RESPONSIVE.DESKTOP_ONLY,
          render: (version: number) => (
            <Tag>{t('common:general.versionFormat', { version })}</Tag>
          ),
        },
      ]
    : []),
  createActionColumn<Repository>({
    width: COLUMN_WIDTHS.ACTIONS_WIDE,
    renderActions: (record) => {
      const buttons: ActionButtonConfig<Repository>[] = [
        {
          type: 'edit',
          icon: <EditOutlined />,
          tooltip: 'common:actions.edit',
          onClick: () => onEdit(record),
          variant: 'primary',
        },
        {
          type: 'trace',
          icon: <HistoryOutlined />,
          tooltip: 'machines:trace',
          onClick: () => onTrace(record),
          variant: 'default',
        },
        {
          type: 'delete',
          icon: <DeleteOutlined />,
          tooltip: 'common:actions.delete',
          onClick: () => onDelete(record),
          variant: 'primary',
          danger: true,
        },
      ];

      return (
        <ActionButtonGroup<Repository>
          buttons={buttons}
          record={record}
          idField="repositoryGuid"
          testIdPrefix="resources-repository"
          t={t}
        />
      );
    },
  }),
];
