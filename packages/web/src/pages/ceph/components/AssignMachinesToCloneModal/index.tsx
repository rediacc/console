import React, { useEffect, useState } from 'react';
import { Tabs } from 'antd';
import { CloudServerOutlined, CopyOutlined } from '@/utils/optimizedIcons';
import { useTranslation } from 'react-i18next';
import {
 useAvailableMachinesForClone,
 useCloneMachines,
 type CephRbdClone,
 type AvailableMachine,
 type CloneMachine,
} from '@/api/queries/ceph';
import {
 useUpdateCloneMachineAssignments,
 useUpdateCloneMachineRemovals,
} from '@/api/queries/cephMutations';
import { showMessage } from '@/utils/messages';
import type { ColumnsType } from 'antd/es/table';
import type { TableRowSelection } from 'antd/es/table/interface';
import LoadingWrapper from '@/components/common/LoadingWrapper';
import { createTruncatedColumn } from '@/components/common/columns';
import { RediaccButton as Button } from '@/components/ui';
import {
 StyledModal,
 TitleStack,
 CloneTag,
 AssignTabContainer,
 ManageTabContainer,
 InfoAlert,
 WarningAlert,
 FieldGroup,
 FieldLabel,
 StyledSelect,
 EmptyState,
 MachinesTable,
 MachineNameRow,
 MachineNameText,
 BridgeTag,
 SelectionCount,
} from './styles';

interface AssignMachinesToCloneModalProps {
 open: boolean;
 clone: CephRbdClone | null;
 poolName: string;
 imageName: string;
 snapshotName: string;
 teamName: string;
 onCancel: () => void;
 onSuccess?: () => void;
}

export const AssignMachinesToCloneModal: React.FC<AssignMachinesToCloneModalProps> = ({
 open,
 clone,
 poolName,
 imageName,
 snapshotName,
 teamName,
 onCancel,
 onSuccess,
}) => {
 const { t } = useTranslation(['ceph', 'machines', 'common']);
 const [selectedMachines, setSelectedMachines] = useState<string[]>([]);
 const [removingMachines, setRemovingMachines] = useState<string[]>([]);
 const [activeTab, setActiveTab] = useState<'assign' | 'manage'>('assign');

 // Fetch available machines
 const { data: availableMachines = [], isLoading: loadingAvailable } =
 useAvailableMachinesForClone(teamName, open && !!clone) as {
 data?: AvailableMachine[];
 isLoading: boolean;
 };

 // Fetch currently assigned machines
 const {
 data: assignedMachines = [],
 isLoading: loadingAssigned,
 refetch: refetchAssigned,
 } = useCloneMachines(
 clone?.cloneName || '',
 snapshotName,
 imageName,
 poolName,
 teamName,
 open && !!clone
 ) as { data?: CloneMachine[]; isLoading: boolean; refetch: () => Promise<unknown> };

 // Mutations
 const assignMutation = useUpdateCloneMachineAssignments();
 const removeMutation = useUpdateCloneMachineRemovals();

 useEffect(() => {
 if (open) {
 // eslint-disable-next-line react-hooks/set-state-in-effect
 setSelectedMachines([]);
 setRemovingMachines([]);
 setActiveTab('assign');
 }
 }, [open]);

 const handleAssign = async () => {
 if (!clone || selectedMachines.length === 0) return;

 try {
 await assignMutation.mutateAsync({
 teamName,
 poolName,
 imageName,
 snapshotName,
 cloneName: clone.cloneName,
 machineNames: selectedMachines.join(','),
 });

 showMessage('success', t('ceph:clones.machinesAssignedSuccess'));
 refetchAssigned();
 setSelectedMachines([]);
 onSuccess?.();
 } catch {
 // Error is handled by the mutation
 }
 };

 const handleRemove = async () => {
 if (!clone || removingMachines.length === 0) return;

 try {
 await removeMutation.mutateAsync({
 teamName,
 poolName,
 imageName,
 snapshotName,
 cloneName: clone.cloneName,
 machineNames: removingMachines.join(','),
 });

 showMessage('success', t('ceph:clones.machinesRemovedSuccess'));
 refetchAssigned();
 setRemovingMachines([]);
 onSuccess?.();
 } catch {
 // Error is handled by the mutation
 }
 };

 const renderAssignTab = () => {
 if (loadingAvailable) {
 return (
 <LoadingWrapper loading centered minHeight={160}>
 <div />
 </LoadingWrapper>
 );
 }

 if (availableMachines.length === 0) {
 return <EmptyState description={t('machines:noAvailableMachinesForClone')} />;
 }

 return (
 <AssignTabContainer>
 <InfoAlert
 message={t('ceph:clones.assignMachinesInfo')}
 variant="info"
 showIcon
 />

 <FieldGroup>
 <FieldLabel>{t('ceph:machines.selectMachines')}:</FieldLabel>
 <StyledSelect
 fullWidth
 mode="multiple"
 placeholder={t('machines:selectMachines')}
 value={selectedMachines}
 onChange={(value) => setSelectedMachines(value as string[])}
 showSearch
 filterOption={(input, option) =>
 (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
 }
 options={availableMachines.map((machine) => ({
 label: machine.machineName,
 value: machine.machineName,
 }))}
 data-testid="assign-clone-machine-select"
 />
 <SelectionCount data-testid="assign-clone-selected-count">
 {t('machines:bulkOperations.selectedCount', { count: selectedMachines.length })}
 </SelectionCount>
 </FieldGroup>
 </AssignTabContainer>
 );
 };

 const renderManageTab = () => {
 if (loadingAssigned) {
 return (
 <LoadingWrapper loading centered minHeight={160}>
 <div />
 </LoadingWrapper>
 );
 }

 if (assignedMachines.length === 0) {
 return <EmptyState description={t('ceph:clones.noMachinesAssigned')} />;
 }

 const machineColumn = createTruncatedColumn<CloneMachine>({
 title: t('machines:machineName'),
 dataIndex: 'machineName',
 key: 'machineName',
 renderWrapper: (content) => (
 <MachineNameRow>
 <CloudServerOutlined />
 <MachineNameText>{content}</MachineNameText>
 </MachineNameRow>
 ),
 });

 const bridgeColumn = createTruncatedColumn<CloneMachine>({
 title: t('machines:bridge'),
 dataIndex: 'bridgeName',
 key: 'bridgeName',
 renderWrapper: (content) => <BridgeTag>{content}</BridgeTag>,
 });

 const columns: ColumnsType<CloneMachine> = [machineColumn, bridgeColumn];
 const rowSelection = {
 selectedRowKeys: removingMachines,
 onChange: (keys: React.Key[]) => setRemovingMachines(keys as string[]),
 getCheckboxProps: (record: CloneMachine) =>
 ({
 'data-testid': `assign-clone-machine-checkbox-${record.machineName}`,
 }) as Record<string, unknown>,
 } as TableRowSelection<CloneMachine>;

 return (
 <ManageTabContainer>
 <WarningAlert
 message={t('ceph:clones.removeMachinesInfo')}
 variant="warning"
 showIcon
 />

 <MachinesTable
 // eslint-disable-next-line @typescript-eslint/no-explicit-any
 rowSelection={rowSelection as any}
 // eslint-disable-next-line @typescript-eslint/no-explicit-any
 columns={columns as any}
 dataSource={assignedMachines}
 rowKey="machineName"
 size="small"
 pagination={false}
 scroll={{ y: 300 }}
 data-testid="assign-clone-machines-table"
 />

 <SelectionCount data-testid="assign-clone-remove-selected-count">
 {t('machines:bulkOperations.selectedCount', { count: removingMachines.length })}
 </SelectionCount>
 </ManageTabContainer>
 );
 };

 const footerButtons =
 activeTab === 'assign'
 ? [
 <Button key="cancel" onClick={onCancel} data-testid="assign-clone-cancel">
 {t('common:actions.cancel')}
 </Button>,
 <Button
 key="assign"
 
 loading={assignMutation.isPending}
 disabled={selectedMachines.length === 0}
 onClick={handleAssign}
 data-testid="assign-clone-submit"
 >
 {t('ceph:machines.assignMachine')}
 </Button>,
 ]
 : [
 <Button key="cancel" onClick={onCancel} data-testid="assign-clone-cancel">
 {t('common:actions.cancel')}
 </Button>,
 <Button
 key="remove"
 variant="danger"
 loading={removeMutation.isPending}
 disabled={removingMachines.length === 0}
 onClick={handleRemove}
 data-testid="assign-clone-remove-submit"
 >
 {t('ceph:machines.unassignMachine')}
 </Button>,
 ];

 return (
 <StyledModal
 data-testid="assign-clone-modal"
 title={
 <TitleStack>
 <CopyOutlined />
 {t('ceph:clones.manageMachines')}
 {clone && <CloneTag>{clone.cloneName}</CloneTag>}
 </TitleStack>
 }
 open={open}
 onCancel={onCancel}
 footer={footerButtons}
 >
 <Tabs
 activeKey={activeTab}
 onChange={(key) => setActiveTab(key as 'assign' | 'manage')}
 data-testid="assign-clone-tabs"
 items={[
 {
 key: 'assign',
 label: t('ceph:clones.assignMachines'),
 children: renderAssignTab(),
 },
 {
 key: 'manage',
 label: t('ceph:clones.assignedMachines'),
 children: renderManageTab(),
 },
 ]}
 />
 </StyledModal>
 );
};
