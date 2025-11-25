import{f as e,g as t,j as s}from"./chunk-DXoLy3RZ.js";import{r as a}from"./chunk-ZRs5Vi2W.js";import{C as n}from"./chunk-BYB5CQV8.js";import{k as i,u as r,M as o,I as c,i as l}from"./chunk-DDg0Spjq.js";import{ah as m,s as d,Q as u,ai as h,a8 as p,a7 as g,B as x,aa as S,e as y,a9 as f,h as b,$ as j,j as $,L as N,W as v,d as K}from"../index-BL9oc91X.js";import{c as C}from"./chunk-Bfi5ED4P.js";import{d as M}from"./chunk-m5fYU7UF.js";import{T as I,a as z}from"./chunk-2wWKRBEk.js";import{i as w,u as A}from"./chunk-BYo3s0jF.js";function k(s){return()=>{const a=e(),n=w.t(`distributedStorage:mutations.operations.${s.operation}`),i=w.t(`distributedStorage:mutations.resources.${s.resourceKey}`),r=w.t("distributedStorage:errors.operationFailed",{operation:n,resource:i}),o=m(r);return t({mutationFn:async e=>{const t=await u.post(s.endpoint,e);return function(e,t){if(0!==e.failure)throw new Error(e.errors?.join(", ")||t)}(t,r),t},onSuccess:(e,t)=>{if(s.getInvalidateKeys(t).forEach(e=>a.invalidateQueries({queryKey:e})),s.additionalInvalidateKeys){s.additionalInvalidateKeys(t).forEach(e=>a.invalidateQueries({queryKey:e}))}d("success",w.t(`distributedStorage:${s.translationKey}`))},onError:o})}}const D=k({endpoint:"/CreateDistributedStorageCluster",operation:"create",resourceKey:"cluster",translationKey:"clusters.createSuccess",getInvalidateKeys:()=>[i.clusters()]}),L=k({endpoint:"/UpdateDistributedStorageClusterVault",operation:"update",resourceKey:"clusterVault",translationKey:"clusters.updateSuccess",getInvalidateKeys:()=>[i.clusters()]}),T=k({endpoint:"/DeleteDistributedStorageCluster",operation:"delete",resourceKey:"cluster",translationKey:"clusters.deleteSuccess",getInvalidateKeys:()=>[i.clusters()]}),E=k({endpoint:"/CreateDistributedStoragePool",operation:"create",resourceKey:"pool",translationKey:"pools.createSuccess",getInvalidateKeys:()=>[i.pools()]}),P=k({endpoint:"/UpdateDistributedStoragePoolVault",operation:"update",resourceKey:"poolVault",translationKey:"pools.updateSuccess",getInvalidateKeys:()=>[i.pools()]}),U=k({endpoint:"/DeleteDistributedStoragePool",operation:"delete",resourceKey:"pool",translationKey:"pools.deleteSuccess",getInvalidateKeys:()=>[i.pools()]}),B=k({endpoint:"/CreateDistributedStorageRbdImage",operation:"create",resourceKey:"rbdImage",translationKey:"images.createSuccess",getInvalidateKeys:()=>[i.images()],additionalInvalidateKeys:()=>[["distributed-storage-cluster-machines"]]}),R=k({endpoint:"/DeleteDistributedStorageRbdImage",operation:"delete",resourceKey:"rbdImage",translationKey:"images.deleteSuccess",getInvalidateKeys:()=>[i.images()]}),W=k({endpoint:"/UpdateImageMachineAssignment",operation:"assign",resourceKey:"imageMachine",translationKey:"images.reassignmentSuccess",getInvalidateKeys:()=>[i.images()]}),F=k({endpoint:"/CreateDistributedStorageRbdSnapshot",operation:"create",resourceKey:"rbdSnapshot",translationKey:"snapshots.createSuccess",getInvalidateKeys:()=>[i.snapshots()]}),O=k({endpoint:"/DeleteDistributedStorageRbdSnapshot",operation:"delete",resourceKey:"rbdSnapshot",translationKey:"snapshots.deleteSuccess",getInvalidateKeys:()=>[i.snapshots()]}),X=k({endpoint:"/CreateDistributedStorageRbdClone",operation:"create",resourceKey:"rbdClone",translationKey:"clones.createSuccess",getInvalidateKeys:()=>[i.clones()]}),V=k({endpoint:"/DeleteDistributedStorageRbdClone",operation:"delete",resourceKey:"rbdClone",translationKey:"clones.deleteSuccess",getInvalidateKeys:()=>[i.clones()]}),G=k({endpoint:"/UpdateMachineDistributedStorage",operation:"update",resourceKey:"machineClusterAssignment",translationKey:"machines.updateSuccess",getInvalidateKeys:e=>[i.clusterMachines(e.clusterName||"")]}),H=k({endpoint:"/UpdateCloneMachineAssignments",operation:"assign",resourceKey:"cloneMachines",translationKey:"clones.machinesAssignedSuccess",getInvalidateKeys:e=>[i.cloneMachines(e.cloneName,e.snapshotName,e.imageName,e.poolName,e.teamName),i.availableMachinesForClone(e.teamName)]}),_=k({endpoint:"/UpdateCloneMachineRemovals",operation:"remove",resourceKey:"cloneMachines",translationKey:"clones.machinesRemovedSuccess",getInvalidateKeys:e=>[i.cloneMachines(e.cloneName,e.snapshotName,e.imageName,e.poolName,e.teamName),i.availableMachinesForClone(e.teamName)]}),Q=k({endpoint:"/UpdateMachineClusterAssignment",operation:"assign",resourceKey:"machineCluster",translationKey:"machines.clusterAssignedSuccess",getInvalidateKeys:e=>[i.clusterMachines(e.clusterName),i.machineAssignmentStatus(e.machineName,e.teamName)]}),q=k({endpoint:"/UpdateMachineClusterRemoval",operation:"remove",resourceKey:"machineCluster",translationKey:"machines.clusterRemovedSuccess",getInvalidateKeys:e=>[["distributed-storage-cluster-machines"],i.machineAssignmentStatus(e.machineName,e.teamName)]}),J=({machine:e})=>{const{data:t,isLoading:a}=r(e.machineName,e.teamName,!e.distributedStorageClusterName);if(e.distributedStorageClusterName)return s.jsx(h,{"data-testid":"machine-status-cell-cluster",children:s.jsx(o,{assignmentType:"CLUSTER",assignmentDetails:`Assigned to cluster: ${e.distributedStorageClusterName}`,size:"small"})});if(a)return s.jsx(h,{$align:"center",children:s.jsx(c,{width:140,height:22,"data-testid":"machine-status-cell-loading"})});if(!t)return s.jsx(h,{"data-testid":"machine-status-cell-available",children:s.jsx(o,{assignmentType:"AVAILABLE",size:"small"})});const n=t,i=(e=>{if(!e)return"AVAILABLE";const t=e.toString().toUpperCase();return"CLUSTER"===t||"IMAGE"===t||"CLONE"===t?t:"AVAILABLE"})(t.assignmentType||n.assignment_type||n.AssignmentType),l=(t.assignmentDetails||n.assignment_details||n.AssignmentDetails)??void 0;return s.jsx(h,{"data-testid":`machine-status-cell-${i.toLowerCase()}`,children:s.jsx(o,{assignmentType:i,assignmentDetails:l,size:"small"})})},{Text:Y}=I,Z=M(x).attrs(({$size:e})=>({className:`${e} assign-to-cluster-modal`}))`
  .ant-modal-body {
    display: flex;
    flex-direction: column;
    gap: ${({theme:e})=>e.spacing.LG}px;
  }
`,ee=M(S)``,te=M(y)`
  width: 100%;
`,se=M(f).attrs({$variant:"info"})``,ae=M(f).attrs({$variant:"warning"})`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
`,ne=M.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,ie=M.div`
  display: inline-flex;
  gap: ${({theme:e})=>e.spacing.XS}px;
  align-items: baseline;
`,re=M(Y)`
  && {
    font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
    color: ${({theme:e})=>e.colors.textPrimary};
  }
`,oe=M(Y)`
  && {
    color: ${({theme:e})=>e.colors.textSecondary};
  }
`,ce=M.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XS}px;
`,le=p,me=M(z)`
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
`,de=g;M.div`
  display: flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`;const ue=M(b)`
  .ant-table-tbody > tr > td {
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,he=M.span`
  display: inline-flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,pe=M(Y)`
  && {
    color: ${({theme:e})=>e.colors.textPrimary};
    font-weight: ${({theme:e})=>e.fontWeight.MEDIUM};
  }
`,ge=M(j).attrs({$variant:"success",$size:"SM",$borderless:!0})`
  && {
    font-size: ${({theme:e})=>e.fontSize.XS}px;
  }
`,xe=M(j).attrs({$size:"SM"})`
  && {
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.XS}px;
  }
`,Se=({open:e,machine:t,machines:i,onCancel:r,onSuccess:o})=>{const{t:c}=A(["machines","distributedStorage","common"]),m=!!i&&i.length>0,u=m&&i?i:t?[t]:[],[h,p]=a.useState(t?.distributedStorageClusterName||null),g=m&&i?Array.from(new Set(i.map(e=>e.teamName))):t?[t.teamName]:[],{data:x=[],isLoading:S}=l(g,e&&g.length>0),y=G(),f=Q();a.useEffect(()=>{e&&t&&!m?p(t.distributedStorageClusterName||null):e&&m&&p(null)},[e,t,m]);const b=a.useMemo(()=>[C({title:c("machines:machineName"),dataIndex:"machineName",key:"machineName",renderWrapper:e=>s.jsxs(he,{children:[s.jsx(n,{}),s.jsx(pe,{children:e})]})}),C({title:c("machines:team"),dataIndex:"teamName",key:"teamName",renderWrapper:e=>s.jsx(ge,{children:e})}),{title:c("machines:assignmentStatus.title"),key:"currentCluster",render:(e,t)=>t.distributedStorageClusterName?s.jsx(xe,{$variant:"cluster",children:t.distributedStorageClusterName}):s.jsx(xe,{$variant:"available",children:c("machines:assignmentStatus.available")})}],[c]),j=m?$.Large:$.Medium;return s.jsx(Z,{$size:j,title:s.jsxs(ee,{children:[s.jsx(n,{}),c(m?"machines:bulkActions.assignToCluster":t?.distributedStorageClusterName?"machines:changeClusterAssignment":"machines:assignToCluster")]}),open:e,onCancel:r,onOk:async()=>{if(h&&0!==u.length)try{if(m){const e=await Promise.allSettled(u.map(e=>f.mutateAsync({teamName:e.teamName,machineName:e.machineName,clusterName:h}))),t=e.filter(e=>"fulfilled"===e.status).length;0===e.filter(e=>"rejected"===e.status).length?d("success",c("machines:bulkOperations.assignmentSuccess",{count:t})):d("warning",c("machines:bulkOperations.assignmentPartial",{success:t,total:u.length}))}else await y.mutateAsync({teamName:t.teamName,machineName:t.machineName,clusterName:h}),d("success",h?c("machines:clusterAssignedSuccess",{cluster:h}):c("machines:clusterUnassignedSuccess"));o?.(),r()}catch{}},confirmLoading:y.isPending||f.isPending,okText:c("common:actions.save"),cancelText:c("common:actions.cancel"),okButtonProps:{disabled:!h,"data-testid":"ds-assign-cluster-ok-button"},cancelButtonProps:{"data-testid":"ds-assign-cluster-cancel-button"},"data-testid":"ds-assign-cluster-modal",children:s.jsxs(te,{children:[m?s.jsxs(s.Fragment,{children:[s.jsx(se,{message:c("machines:bulkOperations.selectedCount",{count:u.length}),description:c("machines:bulkAssignDescription"),type:"info",showIcon:!0}),s.jsx(ue,{columns:b,dataSource:u,rowKey:"machineName",size:"small",pagination:!1,scroll:{y:200},"data-testid":"ds-assign-cluster-bulk-table"})]}):t&&s.jsxs(s.Fragment,{children:[s.jsxs(ne,{children:[s.jsxs(ie,{children:[s.jsxs(re,{children:[c("machines:machine"),":"]}),s.jsx(oe,{children:t.machineName})]}),s.jsxs(ie,{children:[s.jsxs(re,{children:[c("machines:team"),":"]}),s.jsx(oe,{children:t.teamName})]})]}),t.distributedStorageClusterName&&s.jsx(ae,{message:c("machines:currentClusterAssignment",{cluster:t.distributedStorageClusterName}),type:"info",showIcon:!0})]}),s.jsxs(ce,{children:[s.jsxs(le,{children:[c("distributedStorage:clusters.cluster"),":"]}),S?s.jsx(N,{loading:!0,centered:!0,minHeight:80,children:s.jsx("div",{})}):s.jsxs(s.Fragment,{children:[s.jsx(me,{placeholder:c("machines:selectCluster"),value:h,onChange:e=>p(e),showSearch:!0,optionFilterProp:"children","data-testid":"ds-assign-cluster-select",children:x.map(e=>s.jsx(z.Option,{value:e.clusterName,"data-testid":`cluster-option-${e.clusterName}`,children:e.clusterName},e.clusterName))}),!m&&s.jsx(de,{children:c("machines:clusterAssignmentHelp")})]})]})]})})},{Text:ye}=I,fe=M(x).attrs({className:`${$.Medium} remove-from-cluster-modal`})`
  .ant-modal-body {
    display: flex;
    flex-direction: column;
    gap: ${({theme:e})=>e.spacing.LG}px;
  }
`,be=M(S)``,je=M(v)`
  color: ${({theme:e})=>e.colors.error};
  font-size: ${({theme:e})=>e.fontSize.XL}px;
`,$e=M(f).attrs({$variant:"info"})``,Ne=M(f).attrs({$variant:"warning"})`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
`,ve=M(b)`
  .ant-table-tbody > tr > td {
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,Ke=M.span`
  display: inline-flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,Ce=M(ye)`
  && {
    font-size: ${({theme:e})=>e.fontSize.SM}px;
    font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
    color: ${({theme:e})=>e.colors.textPrimary};
  }
`,Me=M(j).attrs({$variant:"cluster",$size:"SM"})`
  && {
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.XS}px;
  }
`,Ie=M(ye)`
  && {
    font-size: ${({theme:e})=>e.fontSize.SM}px;
    color: ${({theme:e})=>e.colors.textSecondary};
  }
`,ze=({open:e,machines:t,selectedMachines:i,allMachines:r,onCancel:o,onSuccess:c})=>{const{t:l}=A(["machines","distributedStorage","common"]),[m,u]=a.useState(!1),h=Q(),p=(t??(i&&r?r.filter(e=>i.includes(e.machineName)):[])).filter(e=>e.distributedStorageClusterName),g=l("common:none"),x=[C({title:l("machines:machineName"),dataIndex:"machineName",key:"machineName",renderWrapper:e=>s.jsxs(Ke,{children:[s.jsx(n,{}),s.jsx(Ce,{children:e})]})}),C({title:l("distributedStorage:clusters.cluster"),dataIndex:"distributedStorageClusterName",key:"cluster",renderText:e=>e||g,renderWrapper:(e,t)=>t===g?s.jsx(Ie,{children:t}):s.jsx(Me,{children:e})})];return s.jsx(fe,{title:s.jsxs(be,{children:[s.jsx(je,{}),l("machines:bulkActions.removeFromCluster")]}),open:e,onOk:async()=>{if(0!==p.length){u(!0);try{const e=await Promise.allSettled(p.map(e=>h.mutateAsync({teamName:e.teamName,machineName:e.machineName,clusterName:""}))),t=e.filter(e=>"fulfilled"===e.status).length;0===e.filter(e=>"rejected"===e.status).length?d("success",l("machines:bulkOperations.removalSuccess",{count:t})):d("warning",l("machines:bulkOperations.assignmentPartial",{success:t,total:p.length})),c&&c(),o()}catch{d("error",l("distributedStorage:machines.unassignError"))}finally{u(!1)}}},onCancel:o,okText:l("common:actions.remove"),cancelText:l("common:actions.cancel"),confirmLoading:m,okButtonProps:{danger:!0,disabled:0===p.length,"data-testid":"ds-remove-cluster-ok-button"},cancelButtonProps:{"data-testid":"ds-remove-cluster-cancel-button"},"data-testid":"ds-remove-cluster-modal",children:0===p.length?s.jsx($e,{message:l("machines:noMachinesWithClusters"),type:"info",showIcon:!0}):s.jsxs(s.Fragment,{children:[s.jsx(Ne,{message:l("machines:removeFromClusterWarning",{count:p.length}),description:l("machines:removeFromClusterDescription"),type:"warning",showIcon:!0}),s.jsx(ve,{columns:x,dataSource:p,rowKey:"machineName",size:"small",pagination:!1,scroll:{y:300},"data-testid":"ds-remove-cluster-table"})]})})},{Text:we}=I,Ae=M(x).attrs({className:`${$.Large} view-assignment-status-modal`})`
  .ant-modal-body {
    display: flex;
    flex-direction: column;
    gap: ${({theme:e})=>e.spacing.LG}px;
  }
`,ke=M(S)``,De=M(K)`
  color: ${({theme:e})=>e.colors.info};
`,Le=M.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({theme:e})=>e.spacing.LG}px;
  margin-bottom: ${({theme:e})=>e.spacing.SM}px;
`,Te=M.div`
  display: inline-flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.XS}px;
`,Ee=M(we)`
  && {
    color: ${({theme:e})=>e.colors.textSecondary};
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,Pe=M(we)`
  && {
    font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
    color: ${({theme:e})=>e.colors.textPrimary};
  }
`,Ue=M(b)`
  .ant-table-tbody > tr > td {
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,Be=M.span`
  display: inline-flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,Re=M(we)`
  && {
    font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
    color: ${({theme:e})=>e.colors.textPrimary};
  }
`,We=M(j).attrs({$variant:"success",$size:"SM",$borderless:!0})`
  && {
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.XS}px;
  }
`,Fe=M(j).attrs({$variant:"cluster",$size:"SM"})`
  && {
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.XS}px;
  }
`,Oe=M(we)`
  && {
    color: ${({theme:e})=>e.colors.textSecondary};
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,Xe=({open:e,machines:t,selectedMachines:a,allMachines:i,onCancel:r})=>{const{t:c}=A(["machines","distributedStorage","common"]),l=t??(a&&i?i.filter(e=>a.includes(e.machineName)):[]),m=c("common:none"),d=C({title:c("machines:machineName"),dataIndex:"machineName",key:"machineName",width:200,renderWrapper:e=>s.jsxs(Be,{children:[s.jsx(n,{}),s.jsx(Re,{children:e})]})}),u=C({title:c("machines:team"),dataIndex:"teamName",key:"teamName",width:150,renderWrapper:e=>s.jsx(We,{children:e})}),h=C({title:c("distributedStorage:clusters.cluster"),dataIndex:"distributedStorageClusterName",key:"cluster",renderText:e=>e||m,renderWrapper:(e,t)=>t===m?s.jsx(Oe,{children:t}):s.jsx(Fe,{children:e})}),p=[d,u,{title:c("machines:assignmentStatus.title"),key:"assignmentStatus",width:200,render:(e,t)=>s.jsx(J,{machine:t})},h],g=l.reduce((e,t)=>(t.distributedStorageClusterName?e.cluster+=1:e.available+=1,e),{available:0,cluster:0}),x=l.length;return s.jsxs(Ae,{title:s.jsxs(ke,{children:[s.jsx(De,{}),c("machines:bulkActions.viewAssignmentStatus")]}),open:e,onCancel:r,footer:null,"data-testid":"ds-view-assignment-status-modal",children:[s.jsxs(Le,{children:[s.jsxs(Te,{children:[s.jsxs(Ee,{children:[c("common:total"),":"]}),s.jsx(Pe,{children:x})]}),s.jsxs(Te,{children:[s.jsx(o,{assignmentType:"AVAILABLE",size:"small"}),s.jsx(Pe,{children:g.available})]}),s.jsxs(Te,{children:[s.jsx(o,{assignmentType:"CLUSTER",size:"small"}),s.jsx(Pe,{children:g.cluster})]})]}),s.jsx(Ue,{columns:p,dataSource:l,rowKey:"machineName",size:"small",pagination:{pageSize:10,showSizeChanger:!1},scroll:{y:400},"data-testid":"ds-view-assignment-status-table"})]})};export{Se as A,J as M,ze as R,Xe as V,q as a,W as b,H as c,_ as d,V as e,X as f,P as g,O as h,F as i,R as j,B as k,D as l,E as m,L as n,T as o,U as p,Q as u};
