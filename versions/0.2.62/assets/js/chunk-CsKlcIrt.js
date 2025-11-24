import{j as e}from"./chunk-jIVxg-O4.js";import{r as t}from"./chunk-DaihG_v-.js";import{C as s}from"./chunk-SHtbEP_b.js";import{u as a,M as i,v as n,C as r,c as o}from"./chunk-ytDy9kGo.js";import{L as c,B as l,d as m,f as d,s as h,W as u,c as g}from"../index-HayqmFIQ.js";import{d as p}from"./chunk-CsUqxJyM.js";import{q as x,T as f,h as $,S,a as b}from"./chunk-hmLtEp7h.js";import{u as y}from"./chunk-DfOmacDz.js";const j=({machine:t})=>{const{data:s,isLoading:n}=a(t.machineName,t.teamName,!t.distributedStorageClusterName);if(t.distributedStorageClusterName)return e.jsx(c,{"data-testid":"machine-status-cell-cluster",children:e.jsx(i,{assignmentType:"CLUSTER",assignmentDetails:`Assigned to cluster: ${t.distributedStorageClusterName}`,size:"small"})});if(n)return e.jsx(c,{$align:"center",children:e.jsx(x,{size:"small","data-testid":"machine-status-cell-loading"})});if(!s)return e.jsx(c,{"data-testid":"machine-status-cell-available",children:e.jsx(i,{assignmentType:"AVAILABLE",size:"small"})});const r=s,o=(e=>{if(!e)return"AVAILABLE";const t=e.toString().toUpperCase();return"CLUSTER"===t||"IMAGE"===t||"CLONE"===t?t:"AVAILABLE"})(s.assignmentType||r.assignment_type||r.AssignmentType),l=(s.assignmentDetails||r.assignment_details||r.AssignmentDetails)??void 0;return e.jsx(c,{"data-testid":`machine-status-cell-${o.toLowerCase()}`,children:e.jsx(i,{assignmentType:o,assignmentDetails:l,size:"small"})})},{Text:N}=f,M=p(l).attrs(({$size:e})=>({className:`${e} assign-to-cluster-modal`}))`
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
`,z=p.div`
  display: flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
  font-size: ${({theme:e})=>e.fontSize.LG}px;
  font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
  color: ${({theme:e})=>e.colors.textPrimary};
`,k=p.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.LG}px;
  width: 100%;
`,C=p($)`
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
  border: 1px solid ${({theme:e})=>e.colors.borderSecondary};
  background-color: ${({theme:e})=>e.colors.bgSecondary};
  padding: ${({theme:e})=>e.spacing.MD}px ${({theme:e})=>e.spacing.LG}px;
`,L=C,v=p(C)`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
`,w=p.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,A=p.div`
  display: inline-flex;
  gap: ${({theme:e})=>e.spacing.XS}px;
  align-items: baseline;
`,I=p(N)`
  && {
    font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
    color: ${({theme:e})=>e.colors.textPrimary};
  }
`,D=p(N)`
  && {
    color: ${({theme:e})=>e.colors.textSecondary};
  }
`,E=p.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XS}px;
`,T=p(N)`
  && {
    font-weight: ${({theme:e})=>e.fontWeight.MEDIUM};
    color: ${({theme:e})=>e.colors.textPrimary};
  }
`,B=p(S)`
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
`,P=p(N)`
  && {
    color: ${({theme:e})=>e.colors.textSecondary};
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`;p.div`
  display: flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`;const O=p(m)`
  .ant-table-tbody > tr > td {
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,G=p.span`
  display: inline-flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,X=p(N)`
  && {
    color: ${({theme:e})=>e.colors.textPrimary};
    font-weight: ${({theme:e})=>e.fontWeight.MEDIUM};
  }
`,W=p(b)`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.MD}px;
    border-color: transparent;
    background-color: ${({theme:e})=>e.colors.bgSuccess};
    color: ${({theme:e})=>e.colors.success};
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.XS}px;
  }
`,R=p(b)`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.MD}px;
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.XS}px;
    border-color: ${({theme:e,$variant:t})=>"cluster"===t?e.colors.primary:e.colors.success};
    color: ${({theme:e,$variant:t})=>"cluster"===t?e.colors.primary:e.colors.success};
    background-color: ${({theme:e,$variant:t})=>"cluster"===t?e.colors.primaryBg:e.colors.bgSuccess};
  }
`,U=({open:a,machine:i,machines:c,onCancel:l,onSuccess:m})=>{const{t:u}=y(["machines","distributedStorage","common"]),g=!!c&&c.length>0,p=g&&c?c:i?[i]:[],[f,$]=t.useState(i?.distributedStorageClusterName||null),b=g&&c?Array.from(new Set(c.map(e=>e.teamName))):i?[i.teamName]:[],{data:j=[],isLoading:N}=n(b,a&&b.length>0),C=r(),U=o();t.useEffect(()=>{a&&i&&!g?$(i.distributedStorageClusterName||null):a&&g&&$(null)},[a,i,g]);const F=t.useMemo(()=>[{title:u("machines:machineName"),dataIndex:"machineName",key:"machineName",render:t=>e.jsxs(G,{children:[e.jsx(s,{}),e.jsx(X,{children:t})]})},{title:u("machines:team"),dataIndex:"teamName",key:"teamName",render:t=>e.jsx(W,{children:t})},{title:u("machines:assignmentStatus.title"),key:"currentCluster",render:(t,s)=>s.distributedStorageClusterName?e.jsx(R,{$variant:"cluster",children:s.distributedStorageClusterName}):e.jsx(R,{$variant:"available",children:u("machines:assignmentStatus.available")})}],[u]),V=g?d.Large:d.Medium;return e.jsx(M,{$size:V,title:e.jsxs(z,{children:[e.jsx(s,{}),u(g?"machines:bulkActions.assignToCluster":i?.distributedStorageClusterName?"machines:changeClusterAssignment":"machines:assignToCluster")]}),open:a,onCancel:l,onOk:async()=>{if(f&&0!==p.length)try{if(g){const e=await Promise.allSettled(p.map(e=>U.mutateAsync({teamName:e.teamName,machineName:e.machineName,clusterName:f}))),t=e.filter(e=>"fulfilled"===e.status).length;0===e.filter(e=>"rejected"===e.status).length?h("success",u("machines:bulkOperations.assignmentSuccess",{count:t})):h("warning",u("machines:bulkOperations.assignmentPartial",{success:t,total:p.length}))}else await C.mutateAsync({teamName:i.teamName,machineName:i.machineName,clusterName:f}),h("success",f?u("machines:clusterAssignedSuccess",{cluster:f}):u("machines:clusterUnassignedSuccess"));m?.(),l()}catch{}},confirmLoading:C.isPending||U.isPending,okText:u("common:actions.save"),cancelText:u("common:actions.cancel"),okButtonProps:{disabled:!f,"data-testid":"ds-assign-cluster-ok-button"},cancelButtonProps:{"data-testid":"ds-assign-cluster-cancel-button"},"data-testid":"ds-assign-cluster-modal",children:e.jsxs(k,{children:[g?e.jsxs(e.Fragment,{children:[e.jsx(L,{message:u("machines:bulkOperations.selectedCount",{count:p.length}),description:u("machines:bulkAssignDescription"),type:"info",showIcon:!0}),e.jsx(O,{columns:F,dataSource:p,rowKey:"machineName",size:"small",pagination:!1,scroll:{y:200},"data-testid":"ds-assign-cluster-bulk-table"})]}):i&&e.jsxs(e.Fragment,{children:[e.jsxs(w,{children:[e.jsxs(A,{children:[e.jsxs(I,{children:[u("machines:machine"),":"]}),e.jsx(D,{children:i.machineName})]}),e.jsxs(A,{children:[e.jsxs(I,{children:[u("machines:team"),":"]}),e.jsx(D,{children:i.teamName})]})]}),i.distributedStorageClusterName&&e.jsx(v,{message:u("machines:currentClusterAssignment",{cluster:i.distributedStorageClusterName}),type:"info",showIcon:!0})]}),e.jsxs(E,{children:[e.jsxs(T,{children:[u("distributedStorage:clusters.cluster"),":"]}),N?e.jsx(x,{size:"small"}):e.jsxs(e.Fragment,{children:[e.jsx(B,{placeholder:u("machines:selectCluster"),value:f,onChange:e=>$(e),showSearch:!0,optionFilterProp:"children","data-testid":"ds-assign-cluster-select",children:j.map(t=>e.jsx(S.Option,{value:t.clusterName,"data-testid":`cluster-option-${t.clusterName}`,children:t.clusterName},t.clusterName))}),!g&&e.jsx(P,{children:u("machines:clusterAssignmentHelp")})]})]})]})})},{Text:F}=f,V=p(l).attrs({className:`${d.Medium} remove-from-cluster-modal`})`
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
`,_=p.div`
  display: flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
  font-size: ${({theme:e})=>e.fontSize.LG}px;
  font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
  color: ${({theme:e})=>e.colors.textPrimary};
`,H=p(u)`
  color: ${({theme:e})=>e.colors.error};
  font-size: ${({theme:e})=>e.fontSize.XL}px;
`,K=p($)`
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
  border: 1px solid ${({theme:e})=>e.colors.borderSecondary};
  background-color: ${({theme:e})=>e.colors.bgSecondary};
  padding: ${({theme:e})=>e.spacing.MD}px ${({theme:e})=>e.spacing.LG}px;
`,q=K,J=p(K)`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
`,Q=p(m)`
  .ant-table-tbody > tr > td {
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,Y=p.span`
  display: inline-flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,Z=p(F)`
  && {
    font-size: ${({theme:e})=>e.fontSize.SM}px;
    font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
    color: ${({theme:e})=>e.colors.textPrimary};
  }
`,ee=p(b)`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.MD}px;
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.XS}px;
    border-color: ${({theme:e})=>e.colors.primary};
    color: ${({theme:e})=>e.colors.primary};
    background-color: ${({theme:e})=>e.colors.primaryBg};
  }
`,te=p(F)`
  && {
    font-size: ${({theme:e})=>e.fontSize.SM}px;
    color: ${({theme:e})=>e.colors.textSecondary};
  }
`,se=({open:a,machines:i,selectedMachines:n,allMachines:r,onCancel:c,onSuccess:l})=>{const{t:m}=y(["machines","distributedStorage","common"]),[d,u]=t.useState(!1),g=o(),p=(i??(n&&r?r.filter(e=>n.includes(e.machineName)):[])).filter(e=>e.distributedStorageClusterName),x=[{title:m("machines:machineName"),dataIndex:"machineName",key:"machineName",render:t=>e.jsxs(Y,{children:[e.jsx(s,{}),e.jsx(Z,{children:t})]})},{title:m("distributedStorage:clusters.cluster"),dataIndex:"distributedStorageClusterName",key:"cluster",render:t=>t?e.jsx(ee,{children:t}):e.jsx(te,{children:m("common:none")})}];return e.jsx(V,{title:e.jsxs(_,{children:[e.jsx(H,{}),m("machines:bulkActions.removeFromCluster")]}),open:a,onOk:async()=>{if(0!==p.length){u(!0);try{const e=await Promise.allSettled(p.map(e=>g.mutateAsync({teamName:e.teamName,machineName:e.machineName,clusterName:""}))),t=e.filter(e=>"fulfilled"===e.status).length;0===e.filter(e=>"rejected"===e.status).length?h("success",m("machines:bulkOperations.removalSuccess",{count:t})):h("warning",m("machines:bulkOperations.assignmentPartial",{success:t,total:p.length})),l&&l(),c()}catch{h("error",m("distributedStorage:machines.unassignError"))}finally{u(!1)}}},onCancel:c,okText:m("common:actions.remove"),cancelText:m("common:actions.cancel"),confirmLoading:d,okButtonProps:{danger:!0,disabled:0===p.length,"data-testid":"ds-remove-cluster-ok-button"},cancelButtonProps:{"data-testid":"ds-remove-cluster-cancel-button"},"data-testid":"ds-remove-cluster-modal",children:0===p.length?e.jsx(q,{message:m("machines:noMachinesWithClusters"),type:"info",showIcon:!0}):e.jsxs(e.Fragment,{children:[e.jsx(J,{message:m("machines:removeFromClusterWarning",{count:p.length}),description:m("machines:removeFromClusterDescription"),type:"warning",showIcon:!0}),e.jsx(Q,{columns:x,dataSource:p,rowKey:"machineName",size:"small",pagination:!1,scroll:{y:300},"data-testid":"ds-remove-cluster-table"})]})})},{Text:ae}=f,ie=p(l).attrs({className:`${d.Large} view-assignment-status-modal`})`
  .ant-modal-body {
    display: flex;
    flex-direction: column;
    gap: ${({theme:e})=>e.spacing.LG}px;
  }
`,ne=p.div`
  display: flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
  color: ${({theme:e})=>e.colors.textPrimary};
  font-size: ${({theme:e})=>e.fontSize.LG}px;
  font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
`,re=p(g)`
  color: ${({theme:e})=>e.colors.info};
`,oe=p.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({theme:e})=>e.spacing.LG}px;
  margin-bottom: ${({theme:e})=>e.spacing.SM}px;
`,ce=p.div`
  display: inline-flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.XS}px;
`,le=p(ae)`
  && {
    color: ${({theme:e})=>e.colors.textSecondary};
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,me=p(ae)`
  && {
    font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
    color: ${({theme:e})=>e.colors.textPrimary};
  }
`,de=p(m)`
  .ant-table-tbody > tr > td {
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,he=p.span`
  display: inline-flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,ue=p(ae)`
  && {
    font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
    color: ${({theme:e})=>e.colors.textPrimary};
  }
`,ge=p(b)`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.MD}px;
    border-color: transparent;
    background-color: ${({theme:e})=>e.colors.bgSuccess};
    color: ${({theme:e})=>e.colors.success};
    font-weight: ${({theme:e})=>e.fontWeight.MEDIUM};
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.XS}px;
  }
`,pe=p(b)`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.MD}px;
    border-color: ${({theme:e})=>e.colors.primary};
    color: ${({theme:e})=>e.colors.primary};
    background-color: ${({theme:e})=>e.colors.primaryBg};
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.XS}px;
  }
`,xe=p(ae)`
  && {
    color: ${({theme:e})=>e.colors.textSecondary};
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,fe=({open:t,machines:a,selectedMachines:n,allMachines:r,onCancel:o})=>{const{t:c}=y(["machines","distributedStorage","common"]),l=a??(n&&r?r.filter(e=>n.includes(e.machineName)):[]),m=[{title:c("machines:machineName"),dataIndex:"machineName",key:"machineName",width:200,render:t=>e.jsxs(he,{children:[e.jsx(s,{}),e.jsx(ue,{children:t})]})},{title:c("machines:team"),dataIndex:"teamName",key:"teamName",width:150,render:t=>e.jsx(ge,{children:t})},{title:c("machines:assignmentStatus.title"),key:"assignmentStatus",width:200,render:(t,s)=>e.jsx(j,{machine:s})},{title:c("distributedStorage:clusters.cluster"),dataIndex:"distributedStorageClusterName",key:"cluster",render:t=>t?e.jsx(pe,{children:t}):e.jsx(xe,{children:c("common:none")})}],d=l.reduce((e,t)=>(t.distributedStorageClusterName?e.cluster+=1:e.available+=1,e),{available:0,cluster:0}),h=l.length;return e.jsxs(ie,{title:e.jsxs(ne,{children:[e.jsx(re,{}),c("machines:bulkActions.viewAssignmentStatus")]}),open:t,onCancel:o,footer:null,"data-testid":"ds-view-assignment-status-modal",children:[e.jsxs(oe,{children:[e.jsxs(ce,{children:[e.jsxs(le,{children:[c("common:total"),":"]}),e.jsx(me,{children:h})]}),e.jsxs(ce,{children:[e.jsx(i,{assignmentType:"AVAILABLE",size:"small"}),e.jsx(me,{children:d.available})]}),e.jsxs(ce,{children:[e.jsx(i,{assignmentType:"CLUSTER",size:"small"}),e.jsx(me,{children:d.cluster})]})]}),e.jsx(de,{columns:m,dataSource:l,rowKey:"machineName",size:"small",pagination:{pageSize:10,showSizeChanger:!1},scroll:{y:400},"data-testid":"ds-view-assignment-status-table"})]})};export{U as A,j as M,se as R,fe as V};
