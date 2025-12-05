import{f as e,g as t,j as a}from"./chunk-DUi8bg1D.js";import{b as s}from"./chunk-DDwtzQW6.js";import{am as n,s as i,_ as r,an as o,ae as l,ad as c,d as m,B as d,ag as u,h,af as g,k as p,a5 as x,C as S,o as N,L as y,W as f,g as b}from"../index-DldRJJRQ.js";import{i as j,u as $,M as v,I as K,g as C}from"./chunk-kTJcUGxe.js";import{c as M}from"./chunk-wiPeo6cG.js";import{M as I}from"./chunk-BveedPc4.js";import{T as z,F as w,a as k}from"./chunk-CX_EivFx.js";import{i as A,u as L}from"./chunk-BQNjmpVv.js";function T(a){return()=>{const s=e(),r=A.t(`distributedStorage:mutations.operations.${a.operation}`),o=A.t(`distributedStorage:mutations.resources.${a.resourceKey}`),l=A.t("distributedStorage:errors.operationFailed",{operation:r,resource:o}),c=n(l);return t({mutationFn:async e=>{await a.request(e)},onSuccess:(e,t)=>{if(a.getInvalidateKeys(t).forEach(e=>s.invalidateQueries({queryKey:e})),a.additionalInvalidateKeys){a.additionalInvalidateKeys(t).forEach(e=>s.invalidateQueries({queryKey:e}))}i("success",A.t(`distributedStorage:${a.translationKey}`))},onError:c})}}const q=T({request:e=>r.distributedStorage.createCluster(e.clusterName,e.clusterVault),operation:"create",resourceKey:"cluster",translationKey:"clusters.createSuccess",getInvalidateKeys:()=>[j.clusters()]}),E=T({request:e=>r.distributedStorage.updateClusterVault(e.clusterName,e.clusterVault,e.vaultVersion),operation:"update",resourceKey:"clusterVault",translationKey:"clusters.updateSuccess",getInvalidateKeys:()=>[j.clusters()]}),P=T({request:e=>r.distributedStorage.deleteCluster(e.clusterName),operation:"delete",resourceKey:"cluster",translationKey:"clusters.deleteSuccess",getInvalidateKeys:()=>[j.clusters()]}),V=T({request:e=>r.distributedStorage.createPool(e.teamName,e.clusterName,e.poolName,e.poolVault),operation:"create",resourceKey:"pool",translationKey:"pools.createSuccess",getInvalidateKeys:()=>[j.pools()]}),F=T({request:e=>r.distributedStorage.updatePoolVault(e.teamName,e.poolName,e.poolVault,e.vaultVersion),operation:"update",resourceKey:"poolVault",translationKey:"pools.updateSuccess",getInvalidateKeys:()=>[j.pools()]}),W=T({request:e=>r.distributedStorage.deletePool(e.teamName,e.poolName),operation:"delete",resourceKey:"pool",translationKey:"pools.deleteSuccess",getInvalidateKeys:()=>[j.pools()]}),D=T({request:e=>r.distributedStorage.createImage(e.poolName,e.teamName,e.imageName,e.machineName,e.imageVault),operation:"create",resourceKey:"rbdImage",translationKey:"images.createSuccess",getInvalidateKeys:()=>[j.images()],additionalInvalidateKeys:()=>[["distributed-storage-cluster-machines"]]}),B=T({request:e=>r.distributedStorage.deleteImage(e.poolName,e.teamName,e.imageName),operation:"delete",resourceKey:"rbdImage",translationKey:"images.deleteSuccess",getInvalidateKeys:()=>[j.images()]}),O=T({request:e=>r.distributedStorage.assignMachineToImage(e.poolName,e.teamName,e.imageName,e.newMachineName),operation:"assign",resourceKey:"imageMachine",translationKey:"images.reassignmentSuccess",getInvalidateKeys:()=>[j.images()]}),X=T({request:e=>r.distributedStorage.createSnapshot(e.imageName,e.poolName,e.teamName,e.snapshotName,e.snapshotVault),operation:"create",resourceKey:"rbdSnapshot",translationKey:"snapshots.createSuccess",getInvalidateKeys:()=>[j.snapshots()]}),R=T({request:e=>r.distributedStorage.deleteSnapshot(e.imageName,e.poolName,e.teamName,e.snapshotName),operation:"delete",resourceKey:"rbdSnapshot",translationKey:"snapshots.deleteSuccess",getInvalidateKeys:()=>[j.snapshots()]}),U=T({request:e=>r.distributedStorage.createClone(e.snapshotName,e.imageName,e.poolName,e.teamName,e.cloneName,e.cloneVault),operation:"create",resourceKey:"rbdClone",translationKey:"clones.createSuccess",getInvalidateKeys:()=>[j.clones()]}),G=T({request:e=>r.distributedStorage.deleteClone(e.cloneName,e.snapshotName,e.imageName,e.poolName,e.teamName),operation:"delete",resourceKey:"rbdClone",translationKey:"clones.deleteSuccess",getInvalidateKeys:()=>[j.clones()]}),_=T({request:e=>r.machines.updateDistributedStorage(e.teamName,e.machineName,e.clusterName),operation:"update",resourceKey:"machineClusterAssignment",translationKey:"machines.updateSuccess",getInvalidateKeys:e=>[j.clusterMachines(e.clusterName||"")]}),H=T({request:e=>r.distributedStorage.assignMachinesToClone(e.cloneName,e.snapshotName,e.imageName,e.poolName,e.teamName,e.machineNames),operation:"assign",resourceKey:"cloneMachines",translationKey:"clones.machinesAssignedSuccess",getInvalidateKeys:e=>[j.cloneMachines(e.cloneName,e.snapshotName,e.imageName,e.poolName,e.teamName),j.availableMachinesForClone(e.teamName)]}),Q=T({request:e=>r.distributedStorage.removeMachinesFromClone(e.cloneName,e.snapshotName,e.imageName,e.poolName,e.teamName,e.machineNames),operation:"remove",resourceKey:"cloneMachines",translationKey:"clones.machinesRemovedSuccess",getInvalidateKeys:e=>[j.cloneMachines(e.cloneName,e.snapshotName,e.imageName,e.poolName,e.teamName),j.availableMachinesForClone(e.teamName)]}),J=T({request:e=>r.machines.updateClusterAssignment(e.teamName,e.machineName,e.clusterName),operation:"assign",resourceKey:"machineCluster",translationKey:"machines.clusterAssignedSuccess",getInvalidateKeys:e=>[j.clusterMachines(e.clusterName),j.machineAssignmentStatus(e.machineName,e.teamName)]}),Y=T({request:e=>r.machines.removeFromCluster(e.teamName,e.machineName),operation:"remove",resourceKey:"machineCluster",translationKey:"machines.clusterRemovedSuccess",getInvalidateKeys:e=>[["distributed-storage-cluster-machines"],j.machineAssignmentStatus(e.machineName,e.teamName)]}),Z=({machine:e})=>{const{data:t,isLoading:s}=$(e.machineName,e.teamName,!e.distributedStorageClusterName);if(e.distributedStorageClusterName)return a.jsx(o,{"data-testid":"machine-status-cell-cluster",children:a.jsx(v,{assignmentType:"CLUSTER",assignmentDetails:`Assigned to cluster: ${e.distributedStorageClusterName}`,size:"small"})});if(s)return a.jsx(o,{$align:"center",children:a.jsx(K,{width:140,height:22,"data-testid":"machine-status-cell-loading"})});if(!t)return a.jsx(o,{"data-testid":"machine-status-cell-available",children:a.jsx(v,{assignmentType:"AVAILABLE",size:"small"})});const n=t,i=(e=>{if(!e)return"AVAILABLE";const t=e.toString().toUpperCase();return"CLUSTER"===t||"IMAGE"===t||"CLONE"===t?t:"AVAILABLE"})(t.assignmentType||n.assignment_type||n.AssignmentType),r=(t.assignmentDetails||n.assignment_details||n.AssignmentDetails)??void 0;return a.jsx(o,{"data-testid":`machine-status-cell-${i.toLowerCase()}`,children:a.jsx(v,{assignmentType:i,assignmentDetails:r,size:"small"})})},{Text:ee}=z,te=m(d).attrs(({$size:e})=>({className:`${e} assign-to-cluster-modal`}))`
  .ant-modal-body {
    display: flex;
    flex-direction: column;
    gap: ${({theme:e})=>e.spacing.LG}px;
  }
`,ae=m(u)``,se=m(h)`
  width: 100%;
`,ne=m(g).attrs({$variant:"info"})``,ie=m(g).attrs({$variant:"warning"})`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
`,re=m.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,oe=m.div`
  display: inline-flex;
  gap: ${({theme:e})=>e.spacing.XS}px;
  align-items: baseline;
`,le=m(ee)`
  && {
    font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
    color: ${({theme:e})=>e.colors.textPrimary};
  }
`,ce=m(ee)`
  && {
    color: ${({theme:e})=>e.colors.textSecondary};
  }
`,me=m.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XS}px;
`,de=l,ue=I,he=c;m.div`
  display: flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`;const ge=m(p)`
  .ant-table-tbody > tr > td {
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,pe=m.span`
  display: inline-flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,xe=m(ee)`
  && {
    color: ${({theme:e})=>e.colors.textPrimary};
    font-weight: ${({theme:e})=>e.fontWeight.MEDIUM};
  }
`,Se=m(x).attrs({$variant:"success",$size:"SM",$borderless:!0})`
  && {
    font-size: ${({theme:e})=>e.fontSize.XS}px;
  }
`,Ne=m(x).attrs({$size:"SM"})`
  && {
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.XS}px;
  }
`,ye=({open:e,machine:t,machines:n,onCancel:r,onSuccess:o})=>{const{t:l}=L(["machines","distributedStorage","common"]),c=!!n&&n.length>0,m=c&&n?n:t?[t]:[],[d,u]=s.useState(t?.distributedStorageClusterName||null),h=c&&n?Array.from(new Set(n.map(e=>e.teamName))):t?[t.teamName]:[],{data:g=[],isLoading:p}=C(h,e&&h.length>0),x=_(),f=J();s.useEffect(()=>{e&&t&&!c?u(t.distributedStorageClusterName||null):e&&c&&u(null)},[e,t,c]);const b=s.useMemo(()=>[M({title:l("machines:machineName"),dataIndex:"machineName",key:"machineName",renderWrapper:e=>a.jsxs(pe,{children:[a.jsx(S,{}),a.jsx(xe,{children:e})]})}),M({title:l("machines:team"),dataIndex:"teamName",key:"teamName",renderWrapper:e=>a.jsx(Se,{children:e})}),{title:l("machines:assignmentStatus.title"),key:"currentCluster",render:(e,t)=>t.distributedStorageClusterName?a.jsx(Ne,{$variant:"cluster",children:t.distributedStorageClusterName}):a.jsx(Ne,{$variant:"available",children:l("machines:assignmentStatus.available")})}],[l]),j=c?N.Large:N.Medium;return a.jsx(te,{$size:j,title:a.jsxs(ae,{children:[a.jsx(S,{}),l(c?"machines:bulkActions.assignToCluster":t?.distributedStorageClusterName?"machines:changeClusterAssignment":"machines:assignToCluster")]}),open:e,onCancel:r,onOk:async()=>{if(d&&0!==m.length)try{if(c){const e=await Promise.allSettled(m.map(e=>f.mutateAsync({teamName:e.teamName,machineName:e.machineName,clusterName:d}))),t=e.filter(e=>"fulfilled"===e.status).length;0===e.filter(e=>"rejected"===e.status).length?i("success",l("machines:bulkOperations.assignmentSuccess",{count:t})):i("warning",l("machines:bulkOperations.assignmentPartial",{success:t,total:m.length}))}else await x.mutateAsync({teamName:t.teamName,machineName:t.machineName,clusterName:d}),i("success",d?l("machines:clusterAssignedSuccess",{cluster:d}):l("machines:clusterUnassignedSuccess"));o?.(),r()}catch{}},confirmLoading:x.isPending||f.isPending,okText:l("common:actions.save"),cancelText:l("common:actions.cancel"),okButtonProps:{disabled:!d,"data-testid":"ds-assign-cluster-ok-button"},cancelButtonProps:{"data-testid":"ds-assign-cluster-cancel-button"},"data-testid":"ds-assign-cluster-modal",children:a.jsxs(se,{children:[c?a.jsxs(a.Fragment,{children:[a.jsx(ne,{message:l("machines:bulkOperations.selectedCount",{count:m.length}),description:l("machines:bulkAssignDescription"),type:"info",showIcon:!0}),a.jsx(ge,{as:w,columns:b,dataSource:m,rowKey:"machineName",size:"small",pagination:!1,scroll:{y:200},"data-testid":"ds-assign-cluster-bulk-table"})]}):t&&a.jsxs(a.Fragment,{children:[a.jsxs(re,{children:[a.jsxs(oe,{children:[a.jsxs(le,{children:[l("machines:machine"),":"]}),a.jsx(ce,{children:t.machineName})]}),a.jsxs(oe,{children:[a.jsxs(le,{children:[l("machines:team"),":"]}),a.jsx(ce,{children:t.teamName})]})]}),t.distributedStorageClusterName&&a.jsx(ie,{message:l("machines:currentClusterAssignment",{cluster:t.distributedStorageClusterName}),type:"info",showIcon:!0})]}),a.jsxs(me,{children:[a.jsxs(de,{children:[l("distributedStorage:clusters.cluster"),":"]}),p?a.jsx(y,{loading:!0,centered:!0,minHeight:80,children:a.jsx("div",{})}):a.jsxs(a.Fragment,{children:[a.jsx(ue,{placeholder:l("machines:selectCluster"),value:d,onChange:e=>u(e),showSearch:!0,optionFilterProp:"children","data-testid":"ds-assign-cluster-select",children:g.map(e=>a.jsx(k.Option,{value:e.clusterName,"data-testid":`cluster-option-${e.clusterName}`,children:e.clusterName},e.clusterName))}),!c&&a.jsx(he,{children:l("machines:clusterAssignmentHelp")})]})]})]})})},{Text:fe}=z,be=m(d).attrs({className:`${N.Medium} remove-from-cluster-modal`})`
  .ant-modal-body {
    display: flex;
    flex-direction: column;
    gap: ${({theme:e})=>e.spacing.LG}px;
  }
`,je=m(u)``,$e=m(f)`
  color: ${({theme:e})=>e.colors.error};
  font-size: ${({theme:e})=>e.fontSize.XL}px;
`,ve=m(g).attrs({$variant:"info"})``,Ke=m(g).attrs({$variant:"warning"})`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
`,Ce=m(p)`
  .ant-table-tbody > tr > td {
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,Me=m.span`
  display: inline-flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,Ie=m(fe)`
  && {
    font-size: ${({theme:e})=>e.fontSize.SM}px;
    font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
    color: ${({theme:e})=>e.colors.textPrimary};
  }
`,ze=m(x).attrs({$variant:"cluster",$size:"SM"})`
  && {
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.XS}px;
  }
`,we=m(fe)`
  && {
    font-size: ${({theme:e})=>e.fontSize.SM}px;
    color: ${({theme:e})=>e.colors.textSecondary};
  }
`,ke=({open:e,machines:t,selectedMachines:n,allMachines:r,onCancel:o,onSuccess:l})=>{const{t:c}=L(["machines","distributedStorage","common"]),[m,d]=s.useState(!1),u=J(),h=(t??(n&&r?r.filter(e=>n.includes(e.machineName)):[])).filter(e=>e.distributedStorageClusterName),g=c("common:none"),p=[M({title:c("machines:machineName"),dataIndex:"machineName",key:"machineName",renderWrapper:e=>a.jsxs(Me,{children:[a.jsx(S,{}),a.jsx(Ie,{children:e})]})}),M({title:c("distributedStorage:clusters.cluster"),dataIndex:"distributedStorageClusterName",key:"cluster",renderText:e=>e||g,renderWrapper:(e,t)=>t===g?a.jsx(we,{children:t}):a.jsx(ze,{children:e})})];return a.jsx(be,{title:a.jsxs(je,{children:[a.jsx($e,{}),c("machines:bulkActions.removeFromCluster")]}),open:e,onOk:async()=>{if(0!==h.length){d(!0);try{const e=await Promise.allSettled(h.map(e=>u.mutateAsync({teamName:e.teamName,machineName:e.machineName,clusterName:""}))),t=e.filter(e=>"fulfilled"===e.status).length;0===e.filter(e=>"rejected"===e.status).length?i("success",c("machines:bulkOperations.removalSuccess",{count:t})):i("warning",c("machines:bulkOperations.assignmentPartial",{success:t,total:h.length})),l&&l(),o()}catch{i("error",c("distributedStorage:machines.unassignError"))}finally{d(!1)}}},onCancel:o,okText:c("common:actions.remove"),cancelText:c("common:actions.cancel"),confirmLoading:m,okButtonProps:{danger:!0,disabled:0===h.length,"data-testid":"ds-remove-cluster-ok-button"},cancelButtonProps:{"data-testid":"ds-remove-cluster-cancel-button"},"data-testid":"ds-remove-cluster-modal",children:0===h.length?a.jsx(ve,{message:c("machines:noMachinesWithClusters"),type:"info",showIcon:!0}):a.jsxs(a.Fragment,{children:[a.jsx(Ke,{message:c("machines:removeFromClusterWarning",{count:h.length}),description:c("machines:removeFromClusterDescription"),type:"warning",showIcon:!0}),a.jsx(Ce,{as:w,columns:p,dataSource:h,rowKey:"machineName",size:"small",pagination:!1,scroll:{y:300},"data-testid":"ds-remove-cluster-table"})]})})},{Text:Ae}=z,Le=m(d).attrs({className:`${N.Large} view-assignment-status-modal`})`
  .ant-modal-body {
    display: flex;
    flex-direction: column;
    gap: ${({theme:e})=>e.spacing.LG}px;
  }
`,Te=m(u)``,qe=m(b)`
  color: ${({theme:e})=>e.colors.info};
`,Ee=m.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({theme:e})=>e.spacing.LG}px;
  margin-bottom: ${({theme:e})=>e.spacing.SM}px;
`,Pe=m.div`
  display: inline-flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.XS}px;
`,Ve=m(Ae)`
  && {
    color: ${({theme:e})=>e.colors.textSecondary};
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,Fe=m(Ae)`
  && {
    font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
    color: ${({theme:e})=>e.colors.textPrimary};
  }
`,We=m(p)`
  .ant-table-tbody > tr > td {
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,De=m.span`
  display: inline-flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,Be=m(Ae)`
  && {
    font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
    color: ${({theme:e})=>e.colors.textPrimary};
  }
`,Oe=m(x).attrs({$variant:"success",$size:"SM",$borderless:!0})`
  && {
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.XS}px;
  }
`,Xe=m(x).attrs({$variant:"cluster",$size:"SM"})`
  && {
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.XS}px;
  }
`,Re=m(Ae)`
  && {
    color: ${({theme:e})=>e.colors.textSecondary};
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,Ue=({open:e,machines:t,selectedMachines:s,allMachines:n,onCancel:i})=>{const{t:r}=L(["machines","distributedStorage","common"]),o=t??(s&&n?n.filter(e=>s.includes(e.machineName)):[]),l=r("common:none"),c=M({title:r("machines:machineName"),dataIndex:"machineName",key:"machineName",width:200,renderWrapper:e=>a.jsxs(De,{children:[a.jsx(S,{}),a.jsx(Be,{children:e})]})}),m=M({title:r("machines:team"),dataIndex:"teamName",key:"teamName",width:150,renderWrapper:e=>a.jsx(Oe,{children:e})}),d=M({title:r("distributedStorage:clusters.cluster"),dataIndex:"distributedStorageClusterName",key:"cluster",renderText:e=>e||l,renderWrapper:(e,t)=>t===l?a.jsx(Re,{children:t}):a.jsx(Xe,{children:e})}),u=[c,m,{title:r("machines:assignmentStatus.title"),key:"assignmentStatus",width:200,render:(e,t)=>a.jsx(Z,{machine:t})},d],h=o.reduce((e,t)=>(t.distributedStorageClusterName?e.cluster+=1:e.available+=1,e),{available:0,cluster:0}),g=o.length;return a.jsxs(Le,{title:a.jsxs(Te,{children:[a.jsx(qe,{}),r("machines:bulkActions.viewAssignmentStatus")]}),open:e,onCancel:i,footer:null,"data-testid":"ds-view-assignment-status-modal",children:[a.jsxs(Ee,{children:[a.jsxs(Pe,{children:[a.jsxs(Ve,{children:[r("common:total"),":"]}),a.jsx(Fe,{children:g})]}),a.jsxs(Pe,{children:[a.jsx(v,{assignmentType:"AVAILABLE",size:"small"}),a.jsx(Fe,{children:h.available})]}),a.jsxs(Pe,{children:[a.jsx(v,{assignmentType:"CLUSTER",size:"small"}),a.jsx(Fe,{children:h.cluster})]})]}),a.jsx(We,{as:w,columns:u,dataSource:o,rowKey:"machineName",size:"small",pagination:{pageSize:10,showSizeChanger:!1},scroll:{y:400},"data-testid":"ds-view-assignment-status-table"})]})};export{ye as A,Z as M,ke as R,Ue as V,Y as a,O as b,H as c,Q as d,G as e,U as f,F as g,R as h,X as i,B as j,D as k,q as l,V as m,E as n,P as o,W as p,J as u};
