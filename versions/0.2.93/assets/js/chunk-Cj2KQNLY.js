import{f as e,g as t,j as s}from"./chunk-DXoLy3RZ.js";import{r as a}from"./chunk-ZRs5Vi2W.js";import{al as n,s as i,Y as r,am as o,ac as c,ab as l,B as m,ae as d,g as u,ad as h,j as p,a3 as g,C as x,l as S,L as y,W as f,f as b}from"../index-C1snWwcF.js";import{k as j,u as $,M as N,I as v,i as K}from"./chunk-ByVkc5TN.js";import{c as C}from"./chunk-BN5C2CRb.js";import{d as M}from"./chunk-m5fYU7UF.js";import{T as I,a as z}from"./chunk-2wWKRBEk.js";import{i as w,u as A}from"./chunk-BYo3s0jF.js";function k(s){return()=>{const a=e(),o=w.t(`distributedStorage:mutations.operations.${s.operation}`),c=w.t(`distributedStorage:mutations.resources.${s.resourceKey}`),l=w.t("distributedStorage:errors.operationFailed",{operation:o,resource:c}),m=n(l);return t({mutationFn:async e=>{const t=await r.post(s.endpoint,e);return function(e,t){if(0!==e.failure)throw new Error(e.errors?.join(", ")||t)}(t,l),t},onSuccess:(e,t)=>{if(s.getInvalidateKeys(t).forEach(e=>a.invalidateQueries({queryKey:e})),s.additionalInvalidateKeys){s.additionalInvalidateKeys(t).forEach(e=>a.invalidateQueries({queryKey:e}))}i("success",w.t(`distributedStorage:${s.translationKey}`))},onError:m})}}const D=k({endpoint:"/CreateDistributedStorageCluster",operation:"create",resourceKey:"cluster",translationKey:"clusters.createSuccess",getInvalidateKeys:()=>[j.clusters()]}),L=k({endpoint:"/UpdateDistributedStorageClusterVault",operation:"update",resourceKey:"clusterVault",translationKey:"clusters.updateSuccess",getInvalidateKeys:()=>[j.clusters()]}),T=k({endpoint:"/DeleteDistributedStorageCluster",operation:"delete",resourceKey:"cluster",translationKey:"clusters.deleteSuccess",getInvalidateKeys:()=>[j.clusters()]}),E=k({endpoint:"/CreateDistributedStoragePool",operation:"create",resourceKey:"pool",translationKey:"pools.createSuccess",getInvalidateKeys:()=>[j.pools()]}),P=k({endpoint:"/UpdateDistributedStoragePoolVault",operation:"update",resourceKey:"poolVault",translationKey:"pools.updateSuccess",getInvalidateKeys:()=>[j.pools()]}),U=k({endpoint:"/DeleteDistributedStoragePool",operation:"delete",resourceKey:"pool",translationKey:"pools.deleteSuccess",getInvalidateKeys:()=>[j.pools()]}),B=k({endpoint:"/CreateDistributedStorageRbdImage",operation:"create",resourceKey:"rbdImage",translationKey:"images.createSuccess",getInvalidateKeys:()=>[j.images()],additionalInvalidateKeys:()=>[["distributed-storage-cluster-machines"]]}),R=k({endpoint:"/DeleteDistributedStorageRbdImage",operation:"delete",resourceKey:"rbdImage",translationKey:"images.deleteSuccess",getInvalidateKeys:()=>[j.images()]}),W=k({endpoint:"/UpdateImageMachineAssignment",operation:"assign",resourceKey:"imageMachine",translationKey:"images.reassignmentSuccess",getInvalidateKeys:()=>[j.images()]}),F=k({endpoint:"/CreateDistributedStorageRbdSnapshot",operation:"create",resourceKey:"rbdSnapshot",translationKey:"snapshots.createSuccess",getInvalidateKeys:()=>[j.snapshots()]}),O=k({endpoint:"/DeleteDistributedStorageRbdSnapshot",operation:"delete",resourceKey:"rbdSnapshot",translationKey:"snapshots.deleteSuccess",getInvalidateKeys:()=>[j.snapshots()]}),X=k({endpoint:"/CreateDistributedStorageRbdClone",operation:"create",resourceKey:"rbdClone",translationKey:"clones.createSuccess",getInvalidateKeys:()=>[j.clones()]}),V=k({endpoint:"/DeleteDistributedStorageRbdClone",operation:"delete",resourceKey:"rbdClone",translationKey:"clones.deleteSuccess",getInvalidateKeys:()=>[j.clones()]}),G=k({endpoint:"/UpdateMachineDistributedStorage",operation:"update",resourceKey:"machineClusterAssignment",translationKey:"machines.updateSuccess",getInvalidateKeys:e=>[j.clusterMachines(e.clusterName||"")]}),H=k({endpoint:"/UpdateCloneMachineAssignments",operation:"assign",resourceKey:"cloneMachines",translationKey:"clones.machinesAssignedSuccess",getInvalidateKeys:e=>[j.cloneMachines(e.cloneName,e.snapshotName,e.imageName,e.poolName,e.teamName),j.availableMachinesForClone(e.teamName)]}),_=k({endpoint:"/UpdateCloneMachineRemovals",operation:"remove",resourceKey:"cloneMachines",translationKey:"clones.machinesRemovedSuccess",getInvalidateKeys:e=>[j.cloneMachines(e.cloneName,e.snapshotName,e.imageName,e.poolName,e.teamName),j.availableMachinesForClone(e.teamName)]}),q=k({endpoint:"/UpdateMachineClusterAssignment",operation:"assign",resourceKey:"machineCluster",translationKey:"machines.clusterAssignedSuccess",getInvalidateKeys:e=>[j.clusterMachines(e.clusterName),j.machineAssignmentStatus(e.machineName,e.teamName)]}),Q=k({endpoint:"/UpdateMachineClusterRemoval",operation:"remove",resourceKey:"machineCluster",translationKey:"machines.clusterRemovedSuccess",getInvalidateKeys:e=>[["distributed-storage-cluster-machines"],j.machineAssignmentStatus(e.machineName,e.teamName)]}),Y=({machine:e})=>{const{data:t,isLoading:a}=$(e.machineName,e.teamName,!e.distributedStorageClusterName);if(e.distributedStorageClusterName)return s.jsx(o,{"data-testid":"machine-status-cell-cluster",children:s.jsx(N,{assignmentType:"CLUSTER",assignmentDetails:`Assigned to cluster: ${e.distributedStorageClusterName}`,size:"small"})});if(a)return s.jsx(o,{$align:"center",children:s.jsx(v,{width:140,height:22,"data-testid":"machine-status-cell-loading"})});if(!t)return s.jsx(o,{"data-testid":"machine-status-cell-available",children:s.jsx(N,{assignmentType:"AVAILABLE",size:"small"})});const n=t,i=(e=>{if(!e)return"AVAILABLE";const t=e.toString().toUpperCase();return"CLUSTER"===t||"IMAGE"===t||"CLONE"===t?t:"AVAILABLE"})(t.assignmentType||n.assignment_type||n.AssignmentType),r=(t.assignmentDetails||n.assignment_details||n.AssignmentDetails)??void 0;return s.jsx(o,{"data-testid":`machine-status-cell-${i.toLowerCase()}`,children:s.jsx(N,{assignmentType:i,assignmentDetails:r,size:"small"})})},{Text:J}=I,Z=M(m).attrs(({$size:e})=>({className:`${e} assign-to-cluster-modal`}))`
  .ant-modal-body {
    display: flex;
    flex-direction: column;
    gap: ${({theme:e})=>e.spacing.LG}px;
  }
`,ee=M(d)``,te=M(u)`
  width: 100%;
`,se=M(h).attrs({$variant:"info"})``,ae=M(h).attrs({$variant:"warning"})`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
`,ne=M.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,ie=M.div`
  display: inline-flex;
  gap: ${({theme:e})=>e.spacing.XS}px;
  align-items: baseline;
`,re=M(J)`
  && {
    font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
    color: ${({theme:e})=>e.colors.textPrimary};
  }
`,oe=M(J)`
  && {
    color: ${({theme:e})=>e.colors.textSecondary};
  }
`,ce=M.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XS}px;
`,le=c,me=M(z)`
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
`,de=l;M.div`
  display: flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`;const ue=M(p)`
  .ant-table-tbody > tr > td {
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,he=M.span`
  display: inline-flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,pe=M(J)`
  && {
    color: ${({theme:e})=>e.colors.textPrimary};
    font-weight: ${({theme:e})=>e.fontWeight.MEDIUM};
  }
`,ge=M(g).attrs({$variant:"success",$size:"SM",$borderless:!0})`
  && {
    font-size: ${({theme:e})=>e.fontSize.XS}px;
  }
`,xe=M(g).attrs({$size:"SM"})`
  && {
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.XS}px;
  }
`,Se=({open:e,machine:t,machines:n,onCancel:r,onSuccess:o})=>{const{t:c}=A(["machines","distributedStorage","common"]),l=!!n&&n.length>0,m=l&&n?n:t?[t]:[],[d,u]=a.useState(t?.distributedStorageClusterName||null),h=l&&n?Array.from(new Set(n.map(e=>e.teamName))):t?[t.teamName]:[],{data:p=[],isLoading:g}=K(h,e&&h.length>0),f=G(),b=q();a.useEffect(()=>{e&&t&&!l?u(t.distributedStorageClusterName||null):e&&l&&u(null)},[e,t,l]);const j=a.useMemo(()=>[C({title:c("machines:machineName"),dataIndex:"machineName",key:"machineName",renderWrapper:e=>s.jsxs(he,{children:[s.jsx(x,{}),s.jsx(pe,{children:e})]})}),C({title:c("machines:team"),dataIndex:"teamName",key:"teamName",renderWrapper:e=>s.jsx(ge,{children:e})}),{title:c("machines:assignmentStatus.title"),key:"currentCluster",render:(e,t)=>t.distributedStorageClusterName?s.jsx(xe,{$variant:"cluster",children:t.distributedStorageClusterName}):s.jsx(xe,{$variant:"available",children:c("machines:assignmentStatus.available")})}],[c]),$=l?S.Large:S.Medium;return s.jsx(Z,{$size:$,title:s.jsxs(ee,{children:[s.jsx(x,{}),c(l?"machines:bulkActions.assignToCluster":t?.distributedStorageClusterName?"machines:changeClusterAssignment":"machines:assignToCluster")]}),open:e,onCancel:r,onOk:async()=>{if(d&&0!==m.length)try{if(l){const e=await Promise.allSettled(m.map(e=>b.mutateAsync({teamName:e.teamName,machineName:e.machineName,clusterName:d}))),t=e.filter(e=>"fulfilled"===e.status).length;0===e.filter(e=>"rejected"===e.status).length?i("success",c("machines:bulkOperations.assignmentSuccess",{count:t})):i("warning",c("machines:bulkOperations.assignmentPartial",{success:t,total:m.length}))}else await f.mutateAsync({teamName:t.teamName,machineName:t.machineName,clusterName:d}),i("success",d?c("machines:clusterAssignedSuccess",{cluster:d}):c("machines:clusterUnassignedSuccess"));o?.(),r()}catch{}},confirmLoading:f.isPending||b.isPending,okText:c("common:actions.save"),cancelText:c("common:actions.cancel"),okButtonProps:{disabled:!d,"data-testid":"ds-assign-cluster-ok-button"},cancelButtonProps:{"data-testid":"ds-assign-cluster-cancel-button"},"data-testid":"ds-assign-cluster-modal",children:s.jsxs(te,{children:[l?s.jsxs(s.Fragment,{children:[s.jsx(se,{message:c("machines:bulkOperations.selectedCount",{count:m.length}),description:c("machines:bulkAssignDescription"),type:"info",showIcon:!0}),s.jsx(ue,{columns:j,dataSource:m,rowKey:"machineName",size:"small",pagination:!1,scroll:{y:200},"data-testid":"ds-assign-cluster-bulk-table"})]}):t&&s.jsxs(s.Fragment,{children:[s.jsxs(ne,{children:[s.jsxs(ie,{children:[s.jsxs(re,{children:[c("machines:machine"),":"]}),s.jsx(oe,{children:t.machineName})]}),s.jsxs(ie,{children:[s.jsxs(re,{children:[c("machines:team"),":"]}),s.jsx(oe,{children:t.teamName})]})]}),t.distributedStorageClusterName&&s.jsx(ae,{message:c("machines:currentClusterAssignment",{cluster:t.distributedStorageClusterName}),type:"info",showIcon:!0})]}),s.jsxs(ce,{children:[s.jsxs(le,{children:[c("distributedStorage:clusters.cluster"),":"]}),g?s.jsx(y,{loading:!0,centered:!0,minHeight:80,children:s.jsx("div",{})}):s.jsxs(s.Fragment,{children:[s.jsx(me,{placeholder:c("machines:selectCluster"),value:d,onChange:e=>u(e),showSearch:!0,optionFilterProp:"children","data-testid":"ds-assign-cluster-select",children:p.map(e=>s.jsx(z.Option,{value:e.clusterName,"data-testid":`cluster-option-${e.clusterName}`,children:e.clusterName},e.clusterName))}),!l&&s.jsx(de,{children:c("machines:clusterAssignmentHelp")})]})]})]})})},{Text:ye}=I,fe=M(m).attrs({className:`${S.Medium} remove-from-cluster-modal`})`
  .ant-modal-body {
    display: flex;
    flex-direction: column;
    gap: ${({theme:e})=>e.spacing.LG}px;
  }
`,be=M(d)``,je=M(f)`
  color: ${({theme:e})=>e.colors.error};
  font-size: ${({theme:e})=>e.fontSize.XL}px;
`,$e=M(h).attrs({$variant:"info"})``,Ne=M(h).attrs({$variant:"warning"})`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
`,ve=M(p)`
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
`,Me=M(g).attrs({$variant:"cluster",$size:"SM"})`
  && {
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.XS}px;
  }
`,Ie=M(ye)`
  && {
    font-size: ${({theme:e})=>e.fontSize.SM}px;
    color: ${({theme:e})=>e.colors.textSecondary};
  }
`,ze=({open:e,machines:t,selectedMachines:n,allMachines:r,onCancel:o,onSuccess:c})=>{const{t:l}=A(["machines","distributedStorage","common"]),[m,d]=a.useState(!1),u=q(),h=(t??(n&&r?r.filter(e=>n.includes(e.machineName)):[])).filter(e=>e.distributedStorageClusterName),p=l("common:none"),g=[C({title:l("machines:machineName"),dataIndex:"machineName",key:"machineName",renderWrapper:e=>s.jsxs(Ke,{children:[s.jsx(x,{}),s.jsx(Ce,{children:e})]})}),C({title:l("distributedStorage:clusters.cluster"),dataIndex:"distributedStorageClusterName",key:"cluster",renderText:e=>e||p,renderWrapper:(e,t)=>t===p?s.jsx(Ie,{children:t}):s.jsx(Me,{children:e})})];return s.jsx(fe,{title:s.jsxs(be,{children:[s.jsx(je,{}),l("machines:bulkActions.removeFromCluster")]}),open:e,onOk:async()=>{if(0!==h.length){d(!0);try{const e=await Promise.allSettled(h.map(e=>u.mutateAsync({teamName:e.teamName,machineName:e.machineName,clusterName:""}))),t=e.filter(e=>"fulfilled"===e.status).length;0===e.filter(e=>"rejected"===e.status).length?i("success",l("machines:bulkOperations.removalSuccess",{count:t})):i("warning",l("machines:bulkOperations.assignmentPartial",{success:t,total:h.length})),c&&c(),o()}catch{i("error",l("distributedStorage:machines.unassignError"))}finally{d(!1)}}},onCancel:o,okText:l("common:actions.remove"),cancelText:l("common:actions.cancel"),confirmLoading:m,okButtonProps:{danger:!0,disabled:0===h.length,"data-testid":"ds-remove-cluster-ok-button"},cancelButtonProps:{"data-testid":"ds-remove-cluster-cancel-button"},"data-testid":"ds-remove-cluster-modal",children:0===h.length?s.jsx($e,{message:l("machines:noMachinesWithClusters"),type:"info",showIcon:!0}):s.jsxs(s.Fragment,{children:[s.jsx(Ne,{message:l("machines:removeFromClusterWarning",{count:h.length}),description:l("machines:removeFromClusterDescription"),type:"warning",showIcon:!0}),s.jsx(ve,{columns:g,dataSource:h,rowKey:"machineName",size:"small",pagination:!1,scroll:{y:300},"data-testid":"ds-remove-cluster-table"})]})})},{Text:we}=I,Ae=M(m).attrs({className:`${S.Large} view-assignment-status-modal`})`
  .ant-modal-body {
    display: flex;
    flex-direction: column;
    gap: ${({theme:e})=>e.spacing.LG}px;
  }
`,ke=M(d)``,De=M(b)`
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
`,Ue=M(p)`
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
`,We=M(g).attrs({$variant:"success",$size:"SM",$borderless:!0})`
  && {
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.XS}px;
  }
`,Fe=M(g).attrs({$variant:"cluster",$size:"SM"})`
  && {
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.XS}px;
  }
`,Oe=M(we)`
  && {
    color: ${({theme:e})=>e.colors.textSecondary};
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,Xe=({open:e,machines:t,selectedMachines:a,allMachines:n,onCancel:i})=>{const{t:r}=A(["machines","distributedStorage","common"]),o=t??(a&&n?n.filter(e=>a.includes(e.machineName)):[]),c=r("common:none"),l=C({title:r("machines:machineName"),dataIndex:"machineName",key:"machineName",width:200,renderWrapper:e=>s.jsxs(Be,{children:[s.jsx(x,{}),s.jsx(Re,{children:e})]})}),m=C({title:r("machines:team"),dataIndex:"teamName",key:"teamName",width:150,renderWrapper:e=>s.jsx(We,{children:e})}),d=C({title:r("distributedStorage:clusters.cluster"),dataIndex:"distributedStorageClusterName",key:"cluster",renderText:e=>e||c,renderWrapper:(e,t)=>t===c?s.jsx(Oe,{children:t}):s.jsx(Fe,{children:e})}),u=[l,m,{title:r("machines:assignmentStatus.title"),key:"assignmentStatus",width:200,render:(e,t)=>s.jsx(Y,{machine:t})},d],h=o.reduce((e,t)=>(t.distributedStorageClusterName?e.cluster+=1:e.available+=1,e),{available:0,cluster:0}),p=o.length;return s.jsxs(Ae,{title:s.jsxs(ke,{children:[s.jsx(De,{}),r("machines:bulkActions.viewAssignmentStatus")]}),open:e,onCancel:i,footer:null,"data-testid":"ds-view-assignment-status-modal",children:[s.jsxs(Le,{children:[s.jsxs(Te,{children:[s.jsxs(Ee,{children:[r("common:total"),":"]}),s.jsx(Pe,{children:p})]}),s.jsxs(Te,{children:[s.jsx(N,{assignmentType:"AVAILABLE",size:"small"}),s.jsx(Pe,{children:h.available})]}),s.jsxs(Te,{children:[s.jsx(N,{assignmentType:"CLUSTER",size:"small"}),s.jsx(Pe,{children:h.cluster})]})]}),s.jsx(Ue,{columns:u,dataSource:o,rowKey:"machineName",size:"small",pagination:{pageSize:10,showSizeChanger:!1},scroll:{y:400},"data-testid":"ds-view-assignment-status-table"})]})};export{Se as A,Y as M,ze as R,Xe as V,Q as a,W as b,H as c,_ as d,V as e,X as f,P as g,O as h,F as i,R as j,B as k,D as l,E as m,L as n,T as o,U as p,q as u};
