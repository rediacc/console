import { Space, Tag } from 'antd';
import { ActionButtonGroup, type ActionButtonConfig } from '@/components/common/ActionButtonGroup';
import { COLUMN_RESPONSIVE, COLUMN_WIDTHS } from '@/components/common/ResourceListView';
import { featureFlags } from '@/config/featureFlags';
import {
  DeleteOutlined,
  EditOutlined,
  HistoryOutlined,
  InboxOutlined,
} from '@/utils/optimizedIcons';
import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type { GetTeamRepositories_ResultSet1 } from '@rediacc/shared/types';
import { createActionColumn } from '../factories/action';
import type { ColumnsType } from 'antd/es/table';

interface BuildRepositoryColumnsParams {
  t: TypedTFunction;
  onEdit: (repository: GetTeamRepositories_ResultSet1) => void;
  onTrace: (repository: GetTeamRepositories_ResultSet1) => void;
  onDelete: (repository: GetTeamRepositories_ResultSet1) => void;
}

export const buildRepositoryColumns = ({
  t,
  onEdit,
  onTrace,
  onDelete,
}: BuildRepositoryColumnsParams): ColumnsType<GetTeamRepositories_ResultSet1> => [
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
          render: (version: number) => <Tag>{t('common:general.versionFormat', { version })}</Tag>,
        },
      ]
    : []),
  createActionColumn<GetTeamRepositories_ResultSet1>({
    width: COLUMN_WIDTHS.ACTIONS_WIDE,
    renderActions: (record) => {
      const buttons: ActionButtonConfig<GetTeamRepositories_ResultSet1>[] = [
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
        <ActionButtonGroup<GetTeamRepositories_ResultSet1>
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
