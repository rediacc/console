import{f as e,g as t,j as s}from"./chunk-DXoLy3RZ.js";import{r as a}from"./chunk-ZRs5Vi2W.js";import{C as n}from"./chunk-pzS3TSBi.js";import{k as i,u as r,M as o,I as c,i as l}from"./chunk-BEielPm8.js";import{Y as m,s as d,z as h,Z as u,B as p,d as g,f as x,L as S,W as y,c as f}from"../index-CEPyNj08.js";import{c as b}from"./chunk-DYFPw3WY.js";import{d as $}from"./chunk-BtZST8U3.js";import{T as j,h as N,S as v,a as M}from"./chunk-B6OG5Vq-.js";import{i as K,u as C}from"./chunk-BYo3s0jF.js";function I(s){return()=>{const a=e(),n=K.t(`distributedStorage:mutations.operations.${s.operation}`),i=K.t(`distributedStorage:mutations.resources.${s.resourceKey}`),r=K.t("distributedStorage:errors.operationFailed",{operation:n,resource:i}),o=m(r);return t({mutationFn:async e=>{const t=await h.post(s.endpoint,e);return function(e,t){if(0!==e.failure)throw new Error(e.errors?.join(", ")||t)}(t,r),t},onSuccess:(e,t)=>{if(s.getInvalidateKeys(t).forEach(e=>a.invalidateQueries({queryKey:e})),s.additionalInvalidateKeys){s.additionalInvalidateKeys(t).forEach(e=>a.invalidateQueries({queryKey:e}))}d("success",K.t(`distributedStorage:${s.translationKey}`))},onError:o})}}const z=I({endpoint:"/CreateDistributedStorageCluster",operation:"create",resourceKey:"cluster",translationKey:"clusters.createSuccess",getInvalidateKeys:()=>[i.clusters()]}),k=I({endpoint:"/UpdateDistributedStorageClusterVault",operation:"update",resourceKey:"clusterVault",translationKey:"clusters.updateSuccess",getInvalidateKeys:()=>[i.clusters()]}),D=I({endpoint:"/DeleteDistributedStorageCluster",operation:"delete",resourceKey:"cluster",translationKey:"clusters.deleteSuccess",getInvalidateKeys:()=>[i.clusters()]}),w=I({endpoint:"/CreateDistributedStoragePool",operation:"create",resourceKey:"pool",translationKey:"pools.createSuccess",getInvalidateKeys:()=>[i.pools()]}),L=I({endpoint:"/UpdateDistributedStoragePoolVault",operation:"update",resourceKey:"poolVault",translationKey:"pools.updateSuccess",getInvalidateKeys:()=>[i.pools()]}),A=I({endpoint:"/DeleteDistributedStoragePool",operation:"delete",resourceKey:"pool",translationKey:"pools.deleteSuccess",getInvalidateKeys:()=>[i.pools()]}),E=I({endpoint:"/CreateDistributedStorageRbdImage",operation:"create",resourceKey:"rbdImage",translationKey:"images.createSuccess",getInvalidateKeys:()=>[i.images()],additionalInvalidateKeys:()=>[["distributed-storage-cluster-machines"]]}),T=I({endpoint:"/DeleteDistributedStorageRbdImage",operation:"delete",resourceKey:"rbdImage",translationKey:"images.deleteSuccess",getInvalidateKeys:()=>[i.images()]}),P=I({endpoint:"/UpdateImageMachineAssignment",operation:"assign",resourceKey:"imageMachine",translationKey:"images.reassignmentSuccess",getInvalidateKeys:()=>[i.images()]}),R=I({endpoint:"/CreateDistributedStorageRbdSnapshot",operation:"create",resourceKey:"rbdSnapshot",translationKey:"snapshots.createSuccess",getInvalidateKeys:()=>[i.snapshots()]}),B=I({endpoint:"/DeleteDistributedStorageRbdSnapshot",operation:"delete",resourceKey:"rbdSnapshot",translationKey:"snapshots.deleteSuccess",getInvalidateKeys:()=>[i.snapshots()]}),W=I({endpoint:"/CreateDistributedStorageRbdClone",operation:"create",resourceKey:"rbdClone",translationKey:"clones.createSuccess",getInvalidateKeys:()=>[i.clones()]}),U=I({endpoint:"/DeleteDistributedStorageRbdClone",operation:"delete",resourceKey:"rbdClone",translationKey:"clones.deleteSuccess",getInvalidateKeys:()=>[i.clones()]}),O=I({endpoint:"/UpdateMachineDistributedStorage",operation:"update",resourceKey:"machineClusterAssignment",translationKey:"machines.updateSuccess",getInvalidateKeys:e=>[i.clusterMachines(e.clusterName||"")]}),G=I({endpoint:"/UpdateCloneMachineAssignments",operation:"assign",resourceKey:"cloneMachines",translationKey:"clones.machinesAssignedSuccess",getInvalidateKeys:e=>[i.cloneMachines(e.cloneName,e.snapshotName,e.imageName,e.poolName,e.teamName),i.availableMachinesForClone(e.teamName)]}),X=I({endpoint:"/UpdateCloneMachineRemovals",operation:"remove",resourceKey:"cloneMachines",translationKey:"clones.machinesRemovedSuccess",getInvalidateKeys:e=>[i.cloneMachines(e.cloneName,e.snapshotName,e.imageName,e.poolName,e.teamName),i.availableMachinesForClone(e.teamName)]}),F=I({endpoint:"/UpdateMachineClusterAssignment",operation:"assign",resourceKey:"machineCluster",translationKey:"machines.clusterAssignedSuccess",getInvalidateKeys:e=>[i.clusterMachines(e.clusterName),i.machineAssignmentStatus(e.machineName,e.teamName)]}),V=I({endpoint:"/UpdateMachineClusterRemoval",operation:"remove",resourceKey:"machineCluster",translationKey:"machines.clusterRemovedSuccess",getInvalidateKeys:e=>[["distributed-storage-cluster-machines"],i.machineAssignmentStatus(e.machineName,e.teamName)]}),H=({machine:e})=>{const{data:t,isLoading:a}=r(e.machineName,e.teamName,!e.distributedStorageClusterName);if(e.distributedStorageClusterName)return s.jsx(u,{"data-testid":"machine-status-cell-cluster",children:s.jsx(o,{assignmentType:"CLUSTER",assignmentDetails:`Assigned to cluster: ${e.distributedStorageClusterName}`,size:"small"})});if(a)return s.jsx(u,{$align:"center",children:s.jsx(c,{width:140,height:22,"data-testid":"machine-status-cell-loading"})});if(!t)return s.jsx(u,{"data-testid":"machine-status-cell-available",children:s.jsx(o,{assignmentType:"AVAILABLE",size:"small"})});const n=t,i=(e=>{if(!e)return"AVAILABLE";const t=e.toString().toUpperCase();return"CLUSTER"===t||"IMAGE"===t||"CLONE"===t?t:"AVAILABLE"})(t.assignmentType||n.assignment_type||n.AssignmentType),l=(t.assignmentDetails||n.assignment_details||n.AssignmentDetails)??void 0;return s.jsx(u,{"data-testid":`machine-status-cell-${i.toLowerCase()}`,children:s.jsx(o,{assignmentType:i,assignmentDetails:l,size:"small"})})},{Text:_}=j,q=$(p).attrs(({$size:e})=>({className:`${e} assign-to-cluster-modal`}))`
  .ant-modal-body {
    display: flex;
    flex-direction: column;
    gap: ${({theme:e})=>e.spacing.LG}px;
  }

  .ant-modal-footer {
    display: flex;
    justify-content: flex-end;
    gap: ${({theme:e})=>e.spacing.SM}px;
  }
`,Q=$.div`
  display: flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
  font-size: ${({theme:e})=>e.fontSize.LG}px;
  font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
  color: ${({theme:e})=>e.colors.textPrimary};
`,Y=$.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.LG}px;
  width: 100%;
`,Z=$(N)`
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
  border: 1px solid ${({theme:e})=>e.colors.borderSecondary};
  background-color: ${({theme:e})=>e.colors.bgSecondary};
  padding: ${({theme:e})=>e.spacing.MD}px ${({theme:e})=>e.spacing.LG}px;
`,J=Z,ee=$(Z)`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
`,te=$.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,se=$.div`
  display: inline-flex;
  gap: ${({theme:e})=>e.spacing.XS}px;
  align-items: baseline;
`,ae=$(_)`
  && {
    font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
    color: ${({theme:e})=>e.colors.textPrimary};
  }
`,ne=$(_)`
  && {
    color: ${({theme:e})=>e.colors.textSecondary};
  }
`,ie=$.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XS}px;
`,re=$(_)`
  && {
    font-weight: ${({theme:e})=>e.fontWeight.MEDIUM};
    color: ${({theme:e})=>e.colors.textPrimary};
  }
`,oe=$(v)`
  && {
    width: 100%;

    .ant-select-selector {
      min-height: ${({theme:e})=>e.dimensions.INPUT_HEIGHT}px;
      border-radius: ${({theme:e})=>e.borderRadius.MD}px !important;
      background-color: ${({theme:e})=>e.colors.inputBg};
      border-color: ${({theme:e})=>e.colors.inputBorder} !important;
      padding: 0 ${({theme:e})=>e.spacing.SM}px;
      transition: ${({theme:e})=>e.transitions.DEFAULT};
    }

    &.ant-select-focused .ant-select-selector {
      border-color: ${({theme:e})=>e.colors.primary} !important;
      box-shadow: 0 0 0 1px ${({theme:e})=>e.colors.primary};
    }
  }
`,ce=$(_)`
  && {
    color: ${({theme:e})=>e.colors.textSecondary};
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`;$.div`
  display: flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`;const le=$(g)`
  .ant-table-tbody > tr > td {
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,me=$.span`
  display: inline-flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,de=$(_)`
  && {
    color: ${({theme:e})=>e.colors.textPrimary};
    font-weight: ${({theme:e})=>e.fontWeight.MEDIUM};
  }
`,he=$(M)`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.MD}px;
    border-color: transparent;
    background-color: ${({theme:e})=>e.colors.bgSuccess};
    color: ${({theme:e})=>e.colors.success};
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.XS}px;
  }
`,ue=$(M)`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.MD}px;
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.XS}px;
    border-color: ${({theme:e,$variant:t})=>"cluster"===t?e.colors.primary:e.colors.success};
    color: ${({theme:e,$variant:t})=>"cluster"===t?e.colors.primary:e.colors.success};
    background-color: ${({theme:e,$variant:t})=>"cluster"===t?e.colors.primaryBg:e.colors.bgSuccess};
  }
`,pe=({open:e,machine:t,machines:i,onCancel:r,onSuccess:o})=>{const{t:c}=C(["machines","distributedStorage","common"]),m=!!i&&i.length>0,h=m&&i?i:t?[t]:[],[u,p]=a.useState(t?.distributedStorageClusterName||null),g=m&&i?Array.from(new Set(i.map(e=>e.teamName))):t?[t.teamName]:[],{data:y=[],isLoading:f}=l(g,e&&g.length>0),$=O(),j=F();a.useEffect(()=>{e&&t&&!m?p(t.distributedStorageClusterName||null):e&&m&&p(null)},[e,t,m]);const N=a.useMemo(()=>[b({title:c("machines:machineName"),dataIndex:"machineName",key:"machineName",renderWrapper:e=>s.jsxs(me,{children:[s.jsx(n,{}),s.jsx(de,{children:e})]})}),b({title:c("machines:team"),dataIndex:"teamName",key:"teamName",renderWrapper:e=>s.jsx(he,{children:e})}),{title:c("machines:assignmentStatus.title"),key:"currentCluster",render:(e,t)=>t.distributedStorageClusterName?s.jsx(ue,{$variant:"cluster",children:t.distributedStorageClusterName}):s.jsx(ue,{$variant:"available",children:c("machines:assignmentStatus.available")})}],[c]),M=m?x.Large:x.Medium;return s.jsx(q,{$size:M,title:s.jsxs(Q,{children:[s.jsx(n,{}),c(m?"machines:bulkActions.assignToCluster":t?.distributedStorageClusterName?"machines:changeClusterAssignment":"machines:assignToCluster")]}),open:e,onCancel:r,onOk:async()=>{if(u&&0!==h.length)try{if(m){const e=await Promise.allSettled(h.map(e=>j.mutateAsync({teamName:e.teamName,machineName:e.machineName,clusterName:u}))),t=e.filter(e=>"fulfilled"===e.status).length;0===e.filter(e=>"rejected"===e.status).length?d("success",c("machines:bulkOperations.assignmentSuccess",{count:t})):d("warning",c("machines:bulkOperations.assignmentPartial",{success:t,total:h.length}))}else await $.mutateAsync({teamName:t.teamName,machineName:t.machineName,clusterName:u}),d("success",u?c("machines:clusterAssignedSuccess",{cluster:u}):c("machines:clusterUnassignedSuccess"));o?.(),r()}catch{}},confirmLoading:$.isPending||j.isPending,okText:c("common:actions.save"),cancelText:c("common:actions.cancel"),okButtonProps:{disabled:!u,"data-testid":"ds-assign-cluster-ok-button"},cancelButtonProps:{"data-testid":"ds-assign-cluster-cancel-button"},"data-testid":"ds-assign-cluster-modal",children:s.jsxs(Y,{children:[m?s.jsxs(s.Fragment,{children:[s.jsx(J,{message:c("machines:bulkOperations.selectedCount",{count:h.length}),description:c("machines:bulkAssignDescription"),type:"info",showIcon:!0}),s.jsx(le,{columns:N,dataSource:h,rowKey:"machineName",size:"small",pagination:!1,scroll:{y:200},"data-testid":"ds-assign-cluster-bulk-table"})]}):t&&s.jsxs(s.Fragment,{children:[s.jsxs(te,{children:[s.jsxs(se,{children:[s.jsxs(ae,{children:[c("machines:machine"),":"]}),s.jsx(ne,{children:t.machineName})]}),s.jsxs(se,{children:[s.jsxs(ae,{children:[c("machines:team"),":"]}),s.jsx(ne,{children:t.teamName})]})]}),t.distributedStorageClusterName&&s.jsx(ee,{message:c("machines:currentClusterAssignment",{cluster:t.distributedStorageClusterName}),type:"info",showIcon:!0})]}),s.jsxs(ie,{children:[s.jsxs(re,{children:[c("distributedStorage:clusters.cluster"),":"]}),f?s.jsx(S,{loading:!0,centered:!0,minHeight:80,children:s.jsx("div",{})}):s.jsxs(s.Fragment,{children:[s.jsx(oe,{placeholder:c("machines:selectCluster"),value:u,onChange:e=>p(e),showSearch:!0,optionFilterProp:"children","data-testid":"ds-assign-cluster-select",children:y.map(e=>s.jsx(v.Option,{value:e.clusterName,"data-testid":`cluster-option-${e.clusterName}`,children:e.clusterName},e.clusterName))}),!m&&s.jsx(ce,{children:c("machines:clusterAssignmentHelp")})]})]})]})})},{Text:ge}=j,xe=$(p).attrs({className:`${x.Medium} remove-from-cluster-modal`})`
  .ant-modal-body {
    display: flex;
    flex-direction: column;
    gap: ${({theme:e})=>e.spacing.LG}px;
  }

  .ant-modal-footer {
    display: flex;
    justify-content: flex-end;
    gap: ${({theme:e})=>e.spacing.SM}px;
  }
`,Se=$.div`
  display: flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
  font-size: ${({theme:e})=>e.fontSize.LG}px;
  font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
  color: ${({theme:e})=>e.colors.textPrimary};
`,ye=$(y)`
  color: ${({theme:e})=>e.colors.error};
  font-size: ${({theme:e})=>e.fontSize.XL}px;
`,fe=$(N)`
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
  border: 1px solid ${({theme:e})=>e.colors.borderSecondary};
  background-color: ${({theme:e})=>e.colors.bgSecondary};
  padding: ${({theme:e})=>e.spacing.MD}px ${({theme:e})=>e.spacing.LG}px;
`,be=fe,$e=$(fe)`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
`,je=$(g)`
  .ant-table-tbody > tr > td {
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,Ne=$.span`
  display: inline-flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,ve=$(ge)`
  && {
    font-size: ${({theme:e})=>e.fontSize.SM}px;
    font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
    color: ${({theme:e})=>e.colors.textPrimary};
  }
`,Me=$(M)`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.MD}px;
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.XS}px;
    border-color: ${({theme:e})=>e.colors.primary};
    color: ${({theme:e})=>e.colors.primary};
    background-color: ${({theme:e})=>e.colors.primaryBg};
  }
`,Ke=$(ge)`
  && {
    font-size: ${({theme:e})=>e.fontSize.SM}px;
    color: ${({theme:e})=>e.colors.textSecondary};
  }
`,Ce=({open:e,machines:t,selectedMachines:i,allMachines:r,onCancel:o,onSuccess:c})=>{const{t:l}=C(["machines","distributedStorage","common"]),[m,h]=a.useState(!1),u=F(),p=(t??(i&&r?r.filter(e=>i.includes(e.machineName)):[])).filter(e=>e.distributedStorageClusterName),g=l("common:none"),x=[b({title:l("machines:machineName"),dataIndex:"machineName",key:"machineName",renderWrapper:e=>s.jsxs(Ne,{children:[s.jsx(n,{}),s.jsx(ve,{children:e})]})}),b({title:l("distributedStorage:clusters.cluster"),dataIndex:"distributedStorageClusterName",key:"cluster",renderText:e=>e||g,renderWrapper:(e,t)=>t===g?s.jsx(Ke,{children:t}):s.jsx(Me,{children:e})})];return s.jsx(xe,{title:s.jsxs(Se,{children:[s.jsx(ye,{}),l("machines:bulkActions.removeFromCluster")]}),open:e,onOk:async()=>{if(0!==p.length){h(!0);try{const e=await Promise.allSettled(p.map(e=>u.mutateAsync({teamName:e.teamName,machineName:e.machineName,clusterName:""}))),t=e.filter(e=>"fulfilled"===e.status).length;0===e.filter(e=>"rejected"===e.status).length?d("success",l("machines:bulkOperations.removalSuccess",{count:t})):d("warning",l("machines:bulkOperations.assignmentPartial",{success:t,total:p.length})),c&&c(),o()}catch{d("error",l("distributedStorage:machines.unassignError"))}finally{h(!1)}}},onCancel:o,okText:l("common:actions.remove"),cancelText:l("common:actions.cancel"),confirmLoading:m,okButtonProps:{danger:!0,disabled:0===p.length,"data-testid":"ds-remove-cluster-ok-button"},cancelButtonProps:{"data-testid":"ds-remove-cluster-cancel-button"},"data-testid":"ds-remove-cluster-modal",children:0===p.length?s.jsx(be,{message:l("machines:noMachinesWithClusters"),type:"info",showIcon:!0}):s.jsxs(s.Fragment,{children:[s.jsx($e,{message:l("machines:removeFromClusterWarning",{count:p.length}),description:l("machines:removeFromClusterDescription"),type:"warning",showIcon:!0}),s.jsx(je,{columns:x,dataSource:p,rowKey:"machineName",size:"small",pagination:!1,scroll:{y:300},"data-testid":"ds-remove-cluster-table"})]})})},{Text:Ie}=j,ze=$(p).attrs({className:`${x.Large} view-assignment-status-modal`})`
  .ant-modal-body {
    display: flex;
    flex-direction: column;
    gap: ${({theme:e})=>e.spacing.LG}px;
  }
`,ke=$.div`
  display: flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
  color: ${({theme:e})=>e.colors.textPrimary};
  font-size: ${({theme:e})=>e.fontSize.LG}px;
  font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
`,De=$(f)`
  color: ${({theme:e})=>e.colors.info};
`,we=$.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({theme:e})=>e.spacing.LG}px;
  margin-bottom: ${({theme:e})=>e.spacing.SM}px;
`,Le=$.div`
  display: inline-flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.XS}px;
`,Ae=$(Ie)`
  && {
    color: ${({theme:e})=>e.colors.textSecondary};
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,Ee=$(Ie)`
  && {
    font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
    color: ${({theme:e})=>e.colors.textPrimary};
  }
`,Te=$(g)`
  .ant-table-tbody > tr > td {
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,Pe=$.span`
  display: inline-flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,Re=$(Ie)`
  && {
    font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
    color: ${({theme:e})=>e.colors.textPrimary};
  }
`,Be=$(M)`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.MD}px;
    border-color: transparent;
    background-color: ${({theme:e})=>e.colors.bgSuccess};
    color: ${({theme:e})=>e.colors.success};
    font-weight: ${({theme:e})=>e.fontWeight.MEDIUM};
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.XS}px;
  }
`,We=$(M)`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.MD}px;
    border-color: ${({theme:e})=>e.colors.primary};
    color: ${({theme:e})=>e.colors.primary};
    background-color: ${({theme:e})=>e.colors.primaryBg};
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.XS}px;
  }
`,Ue=$(Ie)`
  && {
    color: ${({theme:e})=>e.colors.textSecondary};
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,Oe=({open:e,machines:t,selectedMachines:a,allMachines:i,onCancel:r})=>{const{t:c}=C(["machines","distributedStorage","common"]),l=t??(a&&i?i.filter(e=>a.includes(e.machineName)):[]),m=c("common:none"),d=b({title:c("machines:machineName"),dataIndex:"machineName",key:"machineName",width:200,renderWrapper:e=>s.jsxs(Pe,{children:[s.jsx(n,{}),s.jsx(Re,{children:e})]})}),h=b({title:c("machines:team"),dataIndex:"teamName",key:"teamName",width:150,renderWrapper:e=>s.jsx(Be,{children:e})}),u=b({title:c("distributedStorage:clusters.cluster"),dataIndex:"distributedStorageClusterName",key:"cluster",renderText:e=>e||m,renderWrapper:(e,t)=>t===m?s.jsx(Ue,{children:t}):s.jsx(We,{children:e})}),p=[d,h,{title:c("machines:assignmentStatus.title"),key:"assignmentStatus",width:200,render:(e,t)=>s.jsx(H,{machine:t})},u],g=l.reduce((e,t)=>(t.distributedStorageClusterName?e.cluster+=1:e.available+=1,e),{available:0,cluster:0}),x=l.length;return s.jsxs(ze,{title:s.jsxs(ke,{children:[s.jsx(De,{}),c("machines:bulkActions.viewAssignmentStatus")]}),open:e,onCancel:r,footer:null,"data-testid":"ds-view-assignment-status-modal",children:[s.jsxs(we,{children:[s.jsxs(Le,{children:[s.jsxs(Ae,{children:[c("common:total"),":"]}),s.jsx(Ee,{children:x})]}),s.jsxs(Le,{children:[s.jsx(o,{assignmentType:"AVAILABLE",size:"small"}),s.jsx(Ee,{children:g.available})]}),s.jsxs(Le,{children:[s.jsx(o,{assignmentType:"CLUSTER",size:"small"}),s.jsx(Ee,{children:g.cluster})]})]}),s.jsx(Te,{columns:p,dataSource:l,rowKey:"machineName",size:"small",pagination:{pageSize:10,showSizeChanger:!1},scroll:{y:400},"data-testid":"ds-view-assignment-status-table"})]})};export{pe as A,H as M,Ce as R,Oe as V,V as a,P as b,G as c,X as d,U as e,W as f,L as g,B as h,R as i,T as j,E as k,z as l,w as m,k as n,D as o,A as p,F as u};
