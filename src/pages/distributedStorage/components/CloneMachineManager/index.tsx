import { useMemo, useState } from 'react'
import { Table, Spin, Modal, message } from 'antd'
import { useTranslation } from 'react-i18next'
import {
  useGetCloneMachines,
  useGetAvailableMachinesForClone,
  useUpdateCloneMachineAssignments,
  useUpdateCloneMachineRemovals,
  type DistributedStorageRbdClone,
  type DistributedStorageRbdSnapshot,
  type DistributedStorageRbdImage,
  type DistributedStoragePool,
  type CloneMachine,
} from '@/api/queries/distributedStorage'
import { MachineExclusivityWarning } from '@/components/distributedStorage/MachineExclusivityWarning'
import { PlusOutlined } from '@/utils/optimizedIcons'
import { buildCloneMachineColumns } from './columns'
import {
  ManagerCard,
  TableContainer,
  LoadingState,
  EmptyStateWrapper,
  EmptyActionButton,
  WarningWrapper,
} from './styles'
import { HeaderSummary } from './components/HeaderSummary'
import { MachineControls } from './components/MachineControls'
import { AssignMachinesModal } from './components/AssignMachinesModal'

interface CloneMachineManagerProps {
  clone: DistributedStorageRbdClone
  snapshot: DistributedStorageRbdSnapshot
  image: DistributedStorageRbdImage
  pool: DistributedStoragePool
  teamName: string
}

export const CloneMachineManager: React.FC<CloneMachineManagerProps> = ({
  clone,
  snapshot,
  image,
  pool,
  teamName,
}) => {
  const { t } = useTranslation(['distributedStorage', 'machines', 'common'])
  const [searchText, setSearchText] = useState('')
  const [selectedMachines, setSelectedMachines] = useState<string[]>([])
  const [addModalOpen, setAddModalOpen] = useState(false)
  const [selectedNewMachines, setSelectedNewMachines] = useState<string[]>([])
  const [isAdding, setIsAdding] = useState(false)
  const [isRemoving, setIsRemoving] = useState(false)

  const {
    data: assignedMachines = [],
    isLoading: loadingMachines,
    refetch: refetchMachines,
  } = useGetCloneMachines(
    clone.cloneName,
    snapshot.snapshotName,
    image.imageName,
    pool.poolName,
    teamName,
    true,
  )

  const {
    data: availableMachines = [],
    isLoading: loadingAvailable,
  } = useGetAvailableMachinesForClone(teamName, addModalOpen)

  const assignMutation = useUpdateCloneMachineAssignments()
  const removeMutation = useUpdateCloneMachineRemovals()

  const columns = useMemo(
    () =>
      buildCloneMachineColumns({
        t,
        cloneName: clone.cloneName,
      }),
    [clone.cloneName, t],
  )

  const filteredMachines = useMemo(
    () =>
      assignedMachines.filter(
        (machine: any) =>
          machine.machineName.toLowerCase().includes(searchText.toLowerCase()) ||
          machine.bridgeName.toLowerCase().includes(searchText.toLowerCase()),
      ),
    [assignedMachines, searchText],
  )

  const handleAddMachines = () => {
    setAddModalOpen(true)
    setSelectedNewMachines([])
  }

  const handleAssignMachines = async () => {
    if (selectedNewMachines.length === 0) {
      message.warning(t('machines:validation.noMachinesSelected'))
      return
    }

    setIsAdding(true)
    try {
      await assignMutation.mutateAsync({
        teamName,
        poolName: pool.poolName,
        imageName: image.imageName,
        snapshotName: snapshot.snapshotName,
        cloneName: clone.cloneName,
        machineNames: selectedNewMachines.join(','),
      })

      setAddModalOpen(false)
      refetchMachines()
    } catch {
      // handled via showMessage in mutation
    } finally {
      setIsAdding(false)
    }
  }

  const handleRemoveMachines = () => {
    if (selectedMachines.length === 0) {
      message.warning(t('machines:validation.noMachinesSelected'))
      return
    }

    Modal.confirm({
      title: t('machines:removeFromClone'),
      content: t('machines:removeFromClusterWarning', {
        count: selectedMachines.length,
      }),
      okText: t('common:actions.remove'),
      okType: 'danger',
      cancelText: t('common:actions.cancel'),
      okButtonProps: {
        'data-testid': 'clone-manager-confirm-remove-ok',
      },
      cancelButtonProps: {
        'data-testid': 'clone-manager-confirm-remove-cancel',
      },
      onOk: async () => {
        setIsRemoving(true)
        try {
          await removeMutation.mutateAsync({
            teamName,
            poolName: pool.poolName,
            imageName: image.imageName,
            snapshotName: snapshot.snapshotName,
            cloneName: clone.cloneName,
            machineNames: selectedMachines.join(','),
          })

          setSelectedMachines([])
          refetchMachines()
        } catch {
          // handled upstream
        } finally {
          setIsRemoving(false)
        }
      },
    })
  }

  const handleExport = () => {
    const csvContent = [
      ['Machine Name', 'Bridge Name', 'Assignment ID'],
      ...assignedMachines.map((machine: any) => [
        machine.machineName,
        machine.bridgeName,
        machine.assignmentId,
      ]),
    ]
      .map((row) => row.join(','))
      .join('\n')

    const blob = new Blob([csvContent], { type: 'text/csv' })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `clone-${clone.cloneName}-machines.csv`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)

    message.success(t('common:actions.exportSuccess'))
  }

  const rowSelection = {
    selectedRowKeys: selectedMachines,
    onChange: (selectedRowKeys: React.Key[]) => {
      setSelectedMachines(selectedRowKeys as string[])
    },
  }

  return (
    <ManagerCard data-testid="clone-manager-container" bordered={false}>
      <HeaderSummary
        cloneName={clone.cloneName}
        poolName={pool.poolName}
        imageName={image.imageName}
        snapshotName={snapshot.snapshotName}
        totalMachines={assignedMachines.length}
        selectedMachines={selectedMachines.length}
        t={t}
      />

      <MachineControls
        selectedCount={selectedMachines.length}
        assignedCount={assignedMachines.length}
        searchText={searchText}
        isRemoving={isRemoving}
        onAddMachines={handleAddMachines}
        onRemoveMachines={handleRemoveMachines}
        onRefresh={() => refetchMachines()}
        onExport={handleExport}
        onSearchChange={setSearchText}
        t={t}
      />

      <WarningWrapper>
        <MachineExclusivityWarning type="clone" />
      </WarningWrapper>

      {loadingMachines ? (
        <LoadingState data-testid="clone-manager-loading">
          <Spin size="large" />
        </LoadingState>
      ) : assignedMachines.length === 0 ? (
        <EmptyStateWrapper
          description={t('distributedStorage:clones.noMachinesAssigned')}
          data-testid="clone-manager-empty-state"
        >
          <EmptyActionButton
            type="primary"
            icon={<PlusOutlined />}
            onClick={handleAddMachines}
            data-testid="clone-manager-button-add-empty"
          >
            {t('distributedStorage:clones.assignMachines')}
          </EmptyActionButton>
        </EmptyStateWrapper>
      ) : (
        <TableContainer>
          <Table<CloneMachine>
            rowSelection={rowSelection}
            columns={columns}
            dataSource={filteredMachines}
            rowKey="machineName"
            loading={loadingMachines}
            data-testid="clone-manager-table"
            pagination={{
              showSizeChanger: true,
              showTotal: (total, range) =>
                t('common:table.showingRecords', {
                  start: range[0],
                  end: range[1],
                  total,
                }),
            }}
          />
        </TableContainer>
      )}

      <AssignMachinesModal
        open={addModalOpen}
        availableMachines={availableMachines}
        selectedMachines={selectedNewMachines}
        isLoading={loadingAvailable}
        isSubmitting={isAdding}
        onSelectionChange={setSelectedNewMachines}
        onAssign={handleAssignMachines}
        onCancel={() => setAddModalOpen(false)}
        t={t}
      />
    </ManagerCard>
  )
}
