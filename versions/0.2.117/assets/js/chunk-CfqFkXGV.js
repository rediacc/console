import{j as e}from"./chunk-DH1Qig9d.js";import{b as s}from"./chunk-Dx23Oqz1.js";import{al as a,b3 as t,ar as n,d as i,B as c,aF as r,N as m,aD as l,F as o,I as h,b as d,G as u,f as p,aW as g,b4 as x,au as j,C as N,c as f,K as S,k as b,L as v,V as C,W as y,y as $}from"../index-CBjoh7UE.js";import{c as w}from"./chunk-CGNAKPnL.js";import"./chunk-DY6C62bW.js";import{u as z}from"./chunk-DsYhoPUY.js";import{F as k,S as A}from"./chunk-BRjXT_03.js";import{M as L,I as M}from"./chunk-CsADM4pp.js";const I=({machine:s})=>{const{data:n,isLoading:i}=a(s.machineName,s.teamName,!s.cephClusterName);if(s.cephClusterName)return e.jsx(t,{"data-testid":"machine-status-cell-cluster",children:e.jsx(L,{assignmentType:"CLUSTER",assignmentDetails:`Assigned to cluster: ${s.cephClusterName}`,size:"small"})});if(i)return e.jsx(t,{$align:"center",children:e.jsx(M,{width:140,height:22,"data-testid":"machine-status-cell-loading"})});if(!n)return e.jsx(t,{"data-testid":"machine-status-cell-available",children:e.jsx(L,{assignmentType:"AVAILABLE",size:"small"})});const c=n,r=(e=>{if(!e)return"AVAILABLE";const s=e.toString().toUpperCase();return"CLUSTER"===s||"IMAGE"===s||"CLONE"===s?s:"AVAILABLE"})(n.assignmentType||c.assignment_type||c.AssignmentType),m=(n.assignmentDetails||c.assignment_details||c.AssignmentDetails)??void 0;return e.jsx(t,{"data-testid":`machine-status-cell-${r.toLowerCase()}`,children:e.jsx(L,{assignmentType:r,assignmentDetails:m,size:"small"})})},T=i(c).attrs(({$size:e})=>({className:`${e} assign-to-cluster-modal`}))``,W=i(r)``;i(m)`
  width: 100%;
`;const X=i(l).attrs({$variant:"warning"})`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
`,E=i(o).attrs({$gap:"SM"})``,F=i(h).attrs({$align:"flex-start"})`
  gap: ${({theme:e})=>e.spacing.XS}px;
`,P=i(o).attrs({$gap:"XS"})``,B=n;i(d).attrs({$gap:"SM"})``;const D=i(u)`
  .ant-table-tbody > tr > td {
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,O=i(h)``,V=i(p).attrs({preset:"team",size:"sm",borderless:!0})`
  && {
    font-size: ${({theme:e})=>e.fontSize.XS}px;
  }
`,U=i(p).attrs({size:"sm"})`
  && {
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.XS}px;
  }
`,K=({open:a,machine:t,machines:n,onCancel:i,onSuccess:c})=>{const{t:r}=z(["machines","ceph","common"]),m=!!n&&n.length>0,o=m&&n?n:t?[t]:[],[h,d]=s.useState(t?.cephClusterName||null),u=m&&n?Array.from(new Set(n.map(e=>e.teamName))):t?[t.teamName]:[],{data:p=[],isLoading:y}=g(u,a&&u.length>0),$=x(),L=j();s.useEffect(()=>{a&&t&&!m?d(t.cephClusterName||null):a&&m&&d(null)},[a,t,m]);const M=s.useMemo(()=>[w({title:r("machines:machineName"),dataIndex:"machineName",key:"machineName",renderWrapper:s=>e.jsxs(O,{children:[e.jsx(N,{}),e.jsx(f,{weight:"medium",children:s})]})}),w({title:r("machines:team"),dataIndex:"teamName",key:"teamName",renderWrapper:s=>e.jsx(V,{children:s})}),{title:r("machines:assignmentStatus.title"),key:"currentCluster",render:(s,a)=>a.cephClusterName?e.jsx(U,{variant:"primary",children:a.cephClusterName}):e.jsx(U,{variant:"success",children:r("machines:assignmentStatus.available")})}],[r]),I=m?S.Large:S.Medium;return e.jsx(T,{$size:I,title:e.jsxs(W,{children:[e.jsx(N,{}),r(m?"machines:bulkActions.assignToCluster":t?.cephClusterName?"machines:changeClusterAssignment":"machines:assignToCluster")]}),open:a,onCancel:i,onOk:async()=>{if(h&&0!==o.length)try{if(m){const e=await Promise.allSettled(o.map(e=>L.mutateAsync({teamName:e.teamName,machineName:e.machineName,clusterName:h}))),s=e.filter(e=>"fulfilled"===e.status).length;0===e.filter(e=>"rejected"===e.status).length?C("success",r("machines:bulkOperations.assignmentSuccess",{count:s})):C("warning",r("machines:bulkOperations.assignmentPartial",{success:s,total:o.length}))}else await $.mutateAsync({teamName:t.teamName,machineName:t.machineName,clusterName:h}),C("success",h?r("machines:clusterAssignedSuccess",{cluster:h}):r("machines:clusterUnassignedSuccess"));c?.(),i()}catch{}},confirmLoading:$.isPending||L.isPending,okText:r("common:actions.save"),cancelText:r("common:actions.cancel"),okButtonProps:{disabled:!h,"data-testid":"ds-assign-cluster-ok-button"},cancelButtonProps:{"data-testid":"ds-assign-cluster-cancel-button"},"data-testid":"ds-assign-cluster-modal",children:e.jsxs(b,{variant:"spaced-column",fullWidth:!0,children:[m?e.jsxs(e.Fragment,{children:[e.jsx(l,{$variant:"info",message:r("machines:bulkOperations.selectedCount",{count:o.length}),description:r("machines:bulkAssignDescription"),variant:"info",showIcon:!0}),e.jsx(D,{as:k,columns:M,dataSource:o,rowKey:"machineName",size:"small",pagination:!1,scroll:{y:200},"data-testid":"ds-assign-cluster-bulk-table"})]}):t&&e.jsxs(e.Fragment,{children:[e.jsxs(E,{children:[e.jsxs(F,{children:[e.jsxs(f,{weight:"semibold",children:[r("machines:machine"),":"]}),e.jsx(f,{color:"muted",children:t.machineName})]}),e.jsxs(F,{children:[e.jsxs(f,{weight:"semibold",children:[r("machines:team"),":"]}),e.jsx(f,{color:"muted",children:t.teamName})]})]}),t.cephClusterName&&e.jsx(X,{message:r("machines:currentClusterAssignment",{cluster:t.cephClusterName}),variant:"info",showIcon:!0})]}),e.jsxs(P,{children:[e.jsxs(f,{weight:"medium",size:"sm",children:[r("ceph:clusters.cluster"),":"]}),y?e.jsx(v,{loading:!0,centered:!0,minHeight:80,children:e.jsx("div",{})}):e.jsxs(e.Fragment,{children:[e.jsx(B,{fullWidth:!0,placeholder:r("machines:selectCluster"),value:h,onChange:e=>d(e),showSearch:!0,optionFilterProp:"children","data-testid":"ds-assign-cluster-select",children:p.map(s=>e.jsx(A.Option,{value:s.clusterName,"data-testid":`cluster-option-${s.clusterName}`,children:s.clusterName},s.clusterName))}),!m&&e.jsx(f,{size:"xs",color:"muted",children:r("machines:clusterAssignmentHelp")})]})]})]})})},R=i(c).attrs({className:`${S.Medium} remove-from-cluster-modal`})``,G=i(r)``,H=i(y)`
  color: ${({theme:e})=>e.colors.error};
  font-size: ${({theme:e})=>e.fontSize.XL}px;
`,_=i(u)`
  .ant-table-tbody > tr > td {
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,q=i(h)``,J=i(p).attrs({variant:"primary",size:"sm"})`
  && {
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.XS}px;
  }
`,Q=i.div`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
`,Y=({open:a,machines:t,selectedMachines:n,allMachines:i,onCancel:c,onSuccess:r})=>{const{t:m}=z(["machines","ceph","common"]),[o,h]=s.useState(!1),d=j(),u=(t??(n&&i?i.filter(e=>n.includes(e.machineName)):[])).filter(e=>e.cephClusterName),p=m("common:none"),g=[w({title:m("machines:machineName"),dataIndex:"machineName",key:"machineName",renderWrapper:s=>e.jsxs(q,{children:[e.jsx(N,{}),e.jsx(f,{variant:"caption",weight:"semibold",children:s})]})}),w({title:m("ceph:clusters.cluster"),dataIndex:"cephClusterName",key:"cluster",renderText:e=>e||p,renderWrapper:(s,a)=>a===p?e.jsx(f,{variant:"caption",color:"muted",children:a}):e.jsx(J,{children:s})})];return e.jsx(R,{title:e.jsxs(G,{children:[e.jsx(H,{}),m("machines:bulkActions.removeFromCluster")]}),open:a,onOk:async()=>{if(0!==u.length){h(!0);try{const e=await Promise.allSettled(u.map(e=>d.mutateAsync({teamName:e.teamName,machineName:e.machineName,clusterName:""}))),s=e.filter(e=>"fulfilled"===e.status).length;0===e.filter(e=>"rejected"===e.status).length?C("success",m("machines:bulkOperations.removalSuccess",{count:s})):C("warning",m("machines:bulkOperations.assignmentPartial",{success:s,total:u.length})),r&&r(),c()}catch{C("error",m("ceph:machines.unassignError"))}finally{h(!1)}}},onCancel:c,okText:m("common:actions.remove"),cancelText:m("common:actions.cancel"),confirmLoading:o,okButtonProps:{danger:!0,disabled:0===u.length,"data-testid":"ds-remove-cluster-ok-button"},cancelButtonProps:{"data-testid":"ds-remove-cluster-cancel-button"},"data-testid":"ds-remove-cluster-modal",children:0===u.length?e.jsx(l,{$variant:"info",message:m("machines:noMachinesWithClusters"),variant:"info",showIcon:!0}):e.jsxs(e.Fragment,{children:[e.jsx(l,{$variant:"warning",message:m("machines:removeFromClusterWarning",{count:u.length}),description:m("machines:removeFromClusterDescription"),variant:"warning",showIcon:!0,as:Q}),e.jsx(_,{as:k,columns:g,dataSource:u,rowKey:"machineName",size:"small",pagination:!1,scroll:{y:300},"data-testid":"ds-remove-cluster-table"})]})})},Z=i(c).attrs({className:`${S.Large} view-assignment-status-modal`})``,ee=i(r)``,se=i($)`
  color: ${({theme:e})=>e.colors.info};
`,ae=i(d).attrs({$gap:"LG",$wrap:!0})`
  margin-bottom: ${({theme:e})=>e.spacing.SM}px;
`,te=i(h)`
  gap: ${({theme:e})=>e.spacing.XS}px;
`,ne=i(u)`
  .ant-table-tbody > tr > td {
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,ie=i(h)``,ce=i(p).attrs({preset:"team",size:"sm",borderless:!0})`
  && {
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.XS}px;
  }
`,re=i(p).attrs({variant:"primary",size:"sm"})`
  && {
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.XS}px;
  }
`,me=({open:s,machines:a,selectedMachines:t,allMachines:n,onCancel:i})=>{const{t:c}=z(["machines","ceph","common"]),r=a??(t&&n?n.filter(e=>t.includes(e.machineName)):[]),m=c("common:none"),l=w({title:c("machines:machineName"),dataIndex:"machineName",key:"machineName",width:200,renderWrapper:s=>e.jsxs(ie,{children:[e.jsx(N,{}),e.jsx(f,{weight:"semibold",children:s})]})}),o=w({title:c("machines:team"),dataIndex:"teamName",key:"teamName",width:150,renderWrapper:s=>e.jsx(ce,{children:s})}),h=w({title:c("ceph:clusters.cluster"),dataIndex:"cephClusterName",key:"cluster",renderText:e=>e||m,renderWrapper:(s,a)=>a===m?e.jsx(f,{variant:"caption",color:"muted",children:a}):e.jsx(re,{children:s})}),d=[l,o,{title:c("machines:assignmentStatus.title"),key:"assignmentStatus",width:200,render:(s,a)=>e.jsx(I,{machine:a})},h],u=r.reduce((e,s)=>(s.cephClusterName?e.cluster+=1:e.available+=1,e),{available:0,cluster:0}),p=r.length;return e.jsxs(Z,{title:e.jsxs(ee,{children:[e.jsx(se,{}),c("machines:bulkActions.viewAssignmentStatus")]}),open:s,onCancel:i,footer:null,"data-testid":"ds-view-assignment-status-modal",children:[e.jsxs(ae,{children:[e.jsxs(te,{children:[e.jsxs(f,{variant:"caption",color:"muted",children:[c("common:total"),":"]}),e.jsx(f,{weight:"semibold",children:p})]}),e.jsxs(te,{children:[e.jsx(L,{assignmentType:"AVAILABLE",size:"small"}),e.jsx(f,{weight:"semibold",children:u.available})]}),e.jsxs(te,{children:[e.jsx(L,{assignmentType:"CLUSTER",size:"small"}),e.jsx(f,{weight:"semibold",children:u.cluster})]})]}),e.jsx(ne,{as:k,columns:d,dataSource:r,rowKey:"machineName",size:"small",pagination:{pageSize:10,showSizeChanger:!1},scroll:{y:400},"data-testid":"ds-view-assignment-status-table"})]})};export{K as A,I as M,Y as R,me as V};
