import{j as e}from"./chunk-DH1Qig9d.js";import{b as s}from"./chunk-Dx23Oqz1.js";import{an as a,b6 as t,ah as n,d as i,B as c,aI as r,N as m,aG as l,F as o,I as h,b as d,G as u,f as p,aZ as g,b7 as x,ax as j,C as f,c as N,K as S,k as b,L as v,V as C,W as y,y as w}from"../index-BEvUMz1n.js";import{c as $}from"./chunk-bcnw_mXo.js";import"./chunk-B14EaQed.js";import{u as z}from"./chunk-DsYhoPUY.js";import{F as k}from"./chunk-BRjXT_03.js";import{M as A,I as L}from"./chunk-yMucbQiD.js";const M=({machine:s})=>{const{data:n,isLoading:i}=a(s.machineName,s.teamName,!s.cephClusterName);if(s.cephClusterName)return e.jsx(t,{"data-testid":"machine-status-cell-cluster",children:e.jsx(A,{assignmentType:"CLUSTER",assignmentDetails:`Assigned to cluster: ${s.cephClusterName}`,size:"small"})});if(i)return e.jsx(t,{$align:"center",children:e.jsx(L,{width:140,height:22,"data-testid":"machine-status-cell-loading"})});if(!n)return e.jsx(t,{"data-testid":"machine-status-cell-available",children:e.jsx(A,{assignmentType:"AVAILABLE",size:"small"})});const c=n,r=(e=>{if(!e)return"AVAILABLE";const s=e.toString().toUpperCase();return"CLUSTER"===s||"IMAGE"===s||"CLONE"===s?s:"AVAILABLE"})(n.assignmentType||c.assignment_type||c.AssignmentType),m=(n.assignmentDetails||c.assignment_details||c.AssignmentDetails)??void 0;return e.jsx(t,{"data-testid":`machine-status-cell-${r.toLowerCase()}`,children:e.jsx(A,{assignmentType:r,assignmentDetails:m,size:"small"})})},I=i(c).attrs(({$size:e})=>({className:`${e} assign-to-cluster-modal`}))``,T=i(r)``;i(m)`
  width: 100%;
`;const X=i(l).attrs({$variant:"warning"})`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
`,W=i(o).attrs({$gap:"SM"})``,E=i(h).attrs({$align:"flex-start"})`
  gap: ${({theme:e})=>e.spacing.XS}px;
`,P=i(o).attrs({$gap:"XS"})``,F=n;i(d).attrs({$gap:"SM"})``;const B=i(u)`
  .ant-table-tbody > tr > td {
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,D=i(h)``,O=i(p).attrs({preset:"team",size:"sm",borderless:!0})`
  && {
    font-size: ${({theme:e})=>e.fontSize.XS}px;
  }
`,V=i(p).attrs({size:"sm"})`
  && {
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.XS}px;
  }
`,U=({open:a,machine:t,machines:n,onCancel:i,onSuccess:c})=>{const{t:r}=z(["machines","ceph","common"]),m=!!n&&n.length>0,o=m&&n?n:t?[t]:[],[h,d]=s.useState(t?.cephClusterName||null),u=m&&n?Array.from(new Set(n.map(e=>e.teamName))):t?[t.teamName]:[],{data:p=[],isLoading:y}=g(u,a&&u.length>0),w=x(),A=j();s.useEffect(()=>{a&&t&&!m?d(t.cephClusterName||null):a&&m&&d(null)},[a,t,m]);const L=s.useMemo(()=>[$({title:r("machines:machineName"),dataIndex:"machineName",key:"machineName",renderWrapper:s=>e.jsxs(D,{children:[e.jsx(f,{}),e.jsx(N,{weight:"medium",children:s})]})}),$({title:r("machines:team"),dataIndex:"teamName",key:"teamName",renderWrapper:s=>e.jsx(O,{children:s})}),{title:r("machines:assignmentStatus.title"),key:"currentCluster",render:(s,a)=>a.cephClusterName?e.jsx(V,{variant:"primary",children:a.cephClusterName}):e.jsx(V,{variant:"success",children:r("machines:assignmentStatus.available")})}],[r]),M=m?S.Large:S.Medium,U=s.useMemo(()=>p.map(e=>({value:e.clusterName,label:e.clusterName})),[p]);return e.jsx(I,{$size:M,title:e.jsxs(T,{children:[e.jsx(f,{}),r(m?"machines:bulkActions.assignToCluster":t?.cephClusterName?"machines:changeClusterAssignment":"machines:assignToCluster")]}),open:a,onCancel:i,onOk:async()=>{if(h&&0!==o.length)try{if(m){const e=await Promise.allSettled(o.map(e=>A.mutateAsync({teamName:e.teamName,machineName:e.machineName,clusterName:h}))),s=e.filter(e=>"fulfilled"===e.status).length;0===e.filter(e=>"rejected"===e.status).length?C("success",r("machines:bulkOperations.assignmentSuccess",{count:s})):C("warning",r("machines:bulkOperations.assignmentPartial",{success:s,total:o.length}))}else await w.mutateAsync({teamName:t.teamName,machineName:t.machineName,clusterName:h}),C("success",h?r("machines:clusterAssignedSuccess",{cluster:h}):r("machines:clusterUnassignedSuccess"));c?.(),i()}catch{}},confirmLoading:w.isPending||A.isPending,okText:r("common:actions.save"),cancelText:r("common:actions.cancel"),okButtonProps:{disabled:!h,"data-testid":"ds-assign-cluster-ok-button"},cancelButtonProps:{"data-testid":"ds-assign-cluster-cancel-button"},"data-testid":"ds-assign-cluster-modal",children:e.jsxs(b,{variant:"spaced-column",fullWidth:!0,children:[m?e.jsxs(e.Fragment,{children:[e.jsx(l,{$variant:"info",message:r("machines:bulkOperations.selectedCount",{count:o.length}),description:r("machines:bulkAssignDescription"),variant:"info",showIcon:!0}),e.jsx(B,{as:k,columns:L,dataSource:o,rowKey:"machineName",size:"small",pagination:!1,scroll:{y:200},"data-testid":"ds-assign-cluster-bulk-table"})]}):t&&e.jsxs(e.Fragment,{children:[e.jsxs(W,{children:[e.jsxs(E,{children:[e.jsxs(N,{weight:"semibold",children:[r("machines:machine"),":"]}),e.jsx(N,{color:"muted",children:t.machineName})]}),e.jsxs(E,{children:[e.jsxs(N,{weight:"semibold",children:[r("machines:team"),":"]}),e.jsx(N,{color:"muted",children:t.teamName})]})]}),t.cephClusterName&&e.jsx(X,{message:r("machines:currentClusterAssignment",{cluster:t.cephClusterName}),variant:"info",showIcon:!0})]}),e.jsxs(P,{children:[e.jsxs(N,{weight:"medium",size:"sm",children:[r("ceph:clusters.cluster"),":"]}),y?e.jsx(v,{loading:!0,centered:!0,minHeight:80,children:e.jsx("div",{})}):e.jsxs(e.Fragment,{children:[e.jsx(F,{fullWidth:!0,placeholder:r("machines:selectCluster"),value:h,onChange:e=>d(e),showSearch:!0,optionFilterProp:"children",options:U,"data-testid":"ds-assign-cluster-select"}),!m&&e.jsx(N,{size:"xs",color:"muted",children:r("machines:clusterAssignmentHelp")})]})]})]})})},G=i(c).attrs({className:`${S.Medium} remove-from-cluster-modal`})``,K=i(r)``,R=i(y)`
  color: ${({theme:e})=>e.colors.error};
  font-size: ${({theme:e})=>e.fontSize.XL}px;
`,H=i(u)`
  .ant-table-tbody > tr > td {
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,_=i(h)``,Z=i(p).attrs({variant:"primary",size:"sm"})`
  && {
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.XS}px;
  }
`,q=i.div`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
`,J=({open:a,machines:t,selectedMachines:n,allMachines:i,onCancel:c,onSuccess:r})=>{const{t:m}=z(["machines","ceph","common"]),[o,h]=s.useState(!1),d=j(),u=(t??(n&&i?i.filter(e=>n.includes(e.machineName)):[])).filter(e=>e.cephClusterName),p=m("common:none"),g=[$({title:m("machines:machineName"),dataIndex:"machineName",key:"machineName",renderWrapper:s=>e.jsxs(_,{children:[e.jsx(f,{}),e.jsx(N,{variant:"caption",weight:"semibold",children:s})]})}),$({title:m("ceph:clusters.cluster"),dataIndex:"cephClusterName",key:"cluster",renderText:e=>e||p,renderWrapper:(s,a)=>a===p?e.jsx(N,{variant:"caption",color:"muted",children:a}):e.jsx(Z,{children:s})})];return e.jsx(G,{title:e.jsxs(K,{children:[e.jsx(R,{}),m("machines:bulkActions.removeFromCluster")]}),open:a,onOk:async()=>{if(0!==u.length){h(!0);try{const e=await Promise.allSettled(u.map(e=>d.mutateAsync({teamName:e.teamName,machineName:e.machineName,clusterName:""}))),s=e.filter(e=>"fulfilled"===e.status).length;0===e.filter(e=>"rejected"===e.status).length?C("success",m("machines:bulkOperations.removalSuccess",{count:s})):C("warning",m("machines:bulkOperations.assignmentPartial",{success:s,total:u.length})),r&&r(),c()}catch{C("error",m("ceph:machines.unassignError"))}finally{h(!1)}}},onCancel:c,okText:m("common:actions.remove"),cancelText:m("common:actions.cancel"),confirmLoading:o,okButtonProps:{danger:!0,disabled:0===u.length,"data-testid":"ds-remove-cluster-ok-button"},cancelButtonProps:{"data-testid":"ds-remove-cluster-cancel-button"},"data-testid":"ds-remove-cluster-modal",children:0===u.length?e.jsx(l,{$variant:"info",message:m("machines:noMachinesWithClusters"),variant:"info",showIcon:!0}):e.jsxs(e.Fragment,{children:[e.jsx(l,{$variant:"warning",message:m("machines:removeFromClusterWarning",{count:u.length}),description:m("machines:removeFromClusterDescription"),variant:"warning",showIcon:!0,as:q}),e.jsx(H,{as:k,columns:g,dataSource:u,rowKey:"machineName",size:"small",pagination:!1,scroll:{y:300},"data-testid":"ds-remove-cluster-table"})]})})},Q=i(c).attrs({className:`${S.Large} view-assignment-status-modal`})``,Y=i(r)``,ee=i(w)`
  color: ${({theme:e})=>e.colors.info};
`,se=i(d).attrs({$gap:"LG",$wrap:!0})`
  margin-bottom: ${({theme:e})=>e.spacing.SM}px;
`,ae=i(h)`
  gap: ${({theme:e})=>e.spacing.XS}px;
`,te=i(u)`
  .ant-table-tbody > tr > td {
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,ne=i(h)``,ie=i(p).attrs({preset:"team",size:"sm",borderless:!0})`
  && {
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.XS}px;
  }
`,ce=i(p).attrs({variant:"primary",size:"sm"})`
  && {
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.XS}px;
  }
`,re=({open:s,machines:a,selectedMachines:t,allMachines:n,onCancel:i})=>{const{t:c}=z(["machines","ceph","common"]),r=a??(t&&n?n.filter(e=>t.includes(e.machineName)):[]),m=c("common:none"),l=$({title:c("machines:machineName"),dataIndex:"machineName",key:"machineName",width:200,renderWrapper:s=>e.jsxs(ne,{children:[e.jsx(f,{}),e.jsx(N,{weight:"semibold",children:s})]})}),o=$({title:c("machines:team"),dataIndex:"teamName",key:"teamName",width:150,renderWrapper:s=>e.jsx(ie,{children:s})}),h=$({title:c("ceph:clusters.cluster"),dataIndex:"cephClusterName",key:"cluster",renderText:e=>e||m,renderWrapper:(s,a)=>a===m?e.jsx(N,{variant:"caption",color:"muted",children:a}):e.jsx(ce,{children:s})}),d=[l,o,{title:c("machines:assignmentStatus.title"),key:"assignmentStatus",width:200,render:(s,a)=>e.jsx(M,{machine:a})},h],u=r.reduce((e,s)=>(s.cephClusterName?e.cluster+=1:e.available+=1,e),{available:0,cluster:0}),p=r.length;return e.jsxs(Q,{title:e.jsxs(Y,{children:[e.jsx(ee,{}),c("machines:bulkActions.viewAssignmentStatus")]}),open:s,onCancel:i,footer:null,"data-testid":"ds-view-assignment-status-modal",children:[e.jsxs(se,{children:[e.jsxs(ae,{children:[e.jsxs(N,{variant:"caption",color:"muted",children:[c("common:total"),":"]}),e.jsx(N,{weight:"semibold",children:p})]}),e.jsxs(ae,{children:[e.jsx(A,{assignmentType:"AVAILABLE",size:"small"}),e.jsx(N,{weight:"semibold",children:u.available})]}),e.jsxs(ae,{children:[e.jsx(A,{assignmentType:"CLUSTER",size:"small"}),e.jsx(N,{weight:"semibold",children:u.cluster})]})]}),e.jsx(te,{as:k,columns:d,dataSource:r,rowKey:"machineName",size:"small",pagination:{pageSize:10,showSizeChanger:!1},scroll:{y:400},"data-testid":"ds-view-assignment-status-table"})]})};export{U as A,M,J as R,re as V};
