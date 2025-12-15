import{j as e,g as t}from"./chunk-BcoMUYMA.js";import{b as a,f as i,R as n,u as s}from"./chunk-Dx23Oqz1.js";import{u as r,a as o,b as c,c as m,d as l,e as d,f as u}from"./chunk-BS-0Bx1L.js";import{u as h,a as p,F as g,U as x}from"./chunk-gh4o9-lh.js";import{Q as y}from"./chunk-CLCsgqKb.js";import{d as f,B as j,G as b,M as v,F as N,i as k,A as C,c as w,g as $,I as S,J as M,K as I,N as T,O as A,Q as D,U as R,e as E,l as F,p as V,m as P,V as O,X as L,a as z,D as G,j as W,C as _,H as B,Y as Q,Z as X,_ as q,$ as U,T as H,a0 as K,y as Z,a1 as J,z as Y,a2 as ee,a3 as te,a4 as ae,a5 as ie,a6 as ne,a7 as se,a8 as re,a9 as oe,aa as ce,ab as me,ac as le,ad as de,ae as ue}from"../index-BlP7GtlN.js";import{x as he,E as pe,M as ge}from"./chunk-3AIKJ4WW.js";import{T as xe,u as ye}from"./chunk-CK95bpc6.js";import{u as fe}from"./chunk-C6iGxybb.js";import{u as je,A as be,a as ve}from"./chunk-CQvfCnwD.js";import{c as Ne,a as ke,b as Ce}from"./chunk-BeT-rA8y.js";import"./chunk-BFksYpSC.js";import{R as we}from"./chunk-WWAPff2e.js";import{u as $e}from"./chunk-CfWhPMqh.js";import{u as Se,a as Me,W as Ie}from"./chunk-QF6aYlCI.js";import{w as Te,R as Ae}from"./chunk-BchS-fZe.js";import{C as De}from"./chunk-C4OSPEwR.js";import{S as Re}from"./chunk-BWrDyLi3.js";import{u as Ee}from"./chunk-DsYhoPUY.js";import{A as Fe}from"./chunk-jRqAjgpg.js";import{M as Ve,u as Pe,D as Oe,U as Le}from"./chunk-Co55VeR0.js";import{M as ze,A as Ge,R as We,V as _e}from"./chunk-Cf61-0qw.js";import{g as Be}from"./chunk-GqWjj4O2.js";import{B as Qe}from"./chunk-BFmqxisd.js";import{D as Xe,E as qe,L as Ue}from"./chunk-n4Gv56cX.js";import{c as He,a as Ke}from"./chunk-BKxNWyZX.js";import{E as Ze}from"./chunk-BAokIyb5.js";import{F as Je}from"./chunk-CaIZCnow.js";import{c as Ye}from"./chunk-B2-iKkQ1.js";import{R as et}from"./chunk-BBDGMQYU.js";import"./chunk-CQfEgZzF.js";import"./chunk-CWN1N_SP.js";import"./chunk-DB6ez0TU.js";import"./chunk-DHUvGQXX.js";import"./chunk-OPIjZgNK.js";import"./chunk-MVfFrnIr.js";import"./chunk-CDX9nirt.js";import"./chunk-ByXWI8U8.js";import"./chunk-nvdH7hHR.js";import"./chunk-C3a5vxf1.js";import"./chunk-DO4Crfnk.js";import"./chunk-0BlBsXA6.js";import"./chunk-Bi1X1ERN.js";import"./chunk-DQd5xpFD.js";import"./chunk-DSgwHKDs.js";import"./chunk-BuF7wZTp.js";import"./chunk-BSCGvoAZ.js";import"./chunk-DhpoEw86.js";import"./chunk-VcCqKHmd.js";import"./chunk-BEcK6xdI.js";import"./chunk-yhVPGZX_.js";import"./forkTokenService.ts-DeD7Vn3q.js";import"./chunk-DCANEOUJ.js";function tt(e){const{buildQueueVault:t}=Se();je();const i=$e(),{data:n}=Me(),s=a.useCallback(async e=>{try{const a=function(e,t){if(e.teamVault&&"{}"!==e.teamVault)return e.teamVault;const a=t?.find(t=>t.teamName===e.teamName);return a?.vaultContent||"{}"}(e,n),s=await async function(e,t,a){const i=4,n="ping-service",s="{}";return a({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,functionName:"ping",params:{},priority:e.priority||i,addedVia:e.addedVia||n,machineVault:e.machineVault||s,teamVault:t,repositoryVault:e.vaultContent||s})}(e,a,t),r=await async function(e,t,a){const i=4,n=await a.mutateAsync({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,queueVault:t,priority:e.priority||i});return s=n,(e=>{if("object"!=typeof e||null===e)return!1;const t=e,a=void 0===t.taskId||"string"==typeof t.taskId,i=void 0===t.isQueued||"boolean"==typeof t.isQueued;return a&&i})(s)?s:{};var s}(e,s,i);return{taskId:r?.taskId,success:!!r?.taskId||!!r?.isQueued}}catch(a){return{success:!1,error:a instanceof Error?a.message:"Failed to execute ping function"}}},[t,i,n]),r=a.useCallback(async(e,t)=>s({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,priority:t?.priority,description:t?.description,addedVia:t?.addedVia,machineVault:e.vaultContent||"{}"}),[s]),o=a.useCallback(async(e,t)=>{const a=await s(e);if(!a.success||!a.taskId)return a;const i=await Te(a.taskId,t);return{...a,completionResult:i,success:i.success,error:i.success?void 0:i.message}},[s]),c=a.useCallback(async(e,t)=>o({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,priority:t?.priority,description:t?.description,addedVia:t?.addedVia,machineVault:e.vaultContent||"{}"},t?.timeout),[o]);return{executePing:s,executePingForMachine:r,executePingAndWait:o,executePingForMachineAndWait:c,waitForQueueItemCompletion:Te,isLoading:i.isPending}}const at=j`
  0% {
    opacity: 0.65;
  }
  50% {
    opacity: 1;
  }
  100% {
    opacity: 0.65;
  }
`,it=f(b)`
  .ant-modal-body {
    padding: ${({theme:e})=>e.spacing.XL}px;
  }

  .ant-modal-header {
    .ant-modal-title {
      font-size: ${({theme:e})=>e.fontSize.MD}px;
      color: ${({theme:e})=>e.colors.textPrimary};

      .anticon {
        font-size: ${({theme:e})=>e.dimensions.ICON_MD}px;
      }
    }
  }
`,nt=f(v)`
  width: 100%;
`,st=f(N).attrs({$gap:"XS"})``,rt=f(k)`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.LG}px;

    .ant-progress-bg {
      background-image: linear-gradient(
        90deg,
        ${({theme:e})=>e.colors.primary} 0%,
        ${({theme:e})=>e.colors.success} 100%
      );
    }
  }
`,ot=f.div`
  padding: ${({theme:e})=>e.spacing.MD}px;
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
  background-color: ${({theme:e})=>e.colors.bgSecondary};
`,ct=f(C)`
  gap: ${({theme:e})=>e.spacing.XL}px;
`,mt=f(N).attrs({$gap:"XS"})``,lt=f(w).attrs({weight:"semibold"})`
  && {
    color: ${({theme:e,$variant:t})=>"success"===t?e.colors.success:"error"===t?e.colors.error:e.colors.textPrimary};
  }
`,dt=f.div`
  .status-testing td {
    animation: ${at} ${({theme:e})=>e.transitions.SLOW};
    background-color: ${({theme:e})=>e.colors.primaryBg};
  }

  .status-success td {
    background-color: ${({theme:e})=>e.colors.bgSuccess};
  }

  .status-failed td {
    background-color: ${({theme:e})=>e.colors.bgError};
  }
`,ut=f($).attrs({variant:"neutral"})`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.MD}px;
  }
`;f($)`
  && {
    text-transform: capitalize;
  }
`;const ht=f(w)`
  && {
    color: ${({theme:e,$isError:t})=>t?e.colors.error:e.colors.textPrimary};
  }
`,pt=f.div`
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
  font-size: ${({theme:e})=>e.fontSize.SM}px;
`,gt=({open:t,onClose:i,machines:n})=>{const{t:s}=Ee(["machines","common"]),[r,o]=a.useState([]),[c,m]=a.useState(!1),[l,d]=a.useState(0),[u,h]=a.useState(-1),{executePingForMachine:p,waitForQueueItemCompletion:g}=tt();a.useEffect(()=>{if(t&&n.length>0){const e=n.map(e=>({machineName:e.machineName,teamName:e.teamName,bridgeName:e.bridgeName,status:"pending"}));o(e),d(0),h(-1)}},[t,n]);const x=e=>e.success?s("machines:connectionSuccessful"):"TIMEOUT"===e.status?s("machines:testTimeout"):e.message||s("machines:connectionFailed"),y=async(e,t)=>{const a=Date.now();o(e=>e.map((e,a)=>a===t?{...e,status:"testing",timestamp:(new Date).toISOString()}:e));try{const i=await p(e,{priority:4,description:"Connectivity test",addedVia:"connectivity-test"});if(!i.success||!i.taskId)throw new Error(i.error||"Failed to create test task");{o(e=>e.map((e,a)=>a===t?{...e,taskId:i.taskId}:e));const e=await g(i.taskId),n=Date.now()-a;o(a=>a.map((a,i)=>i===t?{...a,status:e.success?"success":"failed",message:x(e),duration:n}:a))}}catch(i){const e=i instanceof Error?i.message:"Failed to create test task",n=Date.now()-a;o(a=>a.map((a,i)=>i===t?{...a,status:"failed",message:e,duration:n}:a))}},f=Ne({title:s("machines:team"),dataIndex:"teamName",key:"teamName",renderWrapper:t=>e.jsx(ut,{children:t})}),j=Ne({title:s("machines:bridge"),dataIndex:"bridgeName",key:"bridgeName",renderWrapper:t=>e.jsx(ut,{children:t})}),b=ke({title:s("machines:status"),dataIndex:"status",key:"status",width:140,statusMap:{pending:{color:"default",label:s("machines:pending"),icon:e.jsx(P,{})},testing:{color:"blue",label:s("machines:testing"),icon:e.jsx(Re,{spin:!0})},success:{color:"success",label:s("machines:connected"),icon:e.jsx(V,{})},failed:{color:"error",label:s("machines:failed"),icon:e.jsx(De,{})}}}),v=Ne({title:s("machines:message"),dataIndex:"message",key:"message",ellipsis:!0,renderText:e=>e||"-"}),N=[{title:s("machines:machineName"),dataIndex:"machineName",key:"machineName",render:(t,a)=>e.jsxs(S,{"data-testid":`connectivity-machine-${t}`,children:[e.jsx(M,{$variant:a.status,children:(()=>{switch(a.status){case"testing":return e.jsx(Re,{spin:!0,"data-testid":`connectivity-status-icon-testing-${t}`});case"success":return e.jsx(V,{"data-testid":`connectivity-status-icon-success-${t}`});case"failed":return e.jsx(De,{"data-testid":`connectivity-status-icon-failed-${t}`});default:return e.jsx(P,{"data-testid":`connectivity-status-icon-pending-${t}`})}})()}),e.jsx(w,{weight:"semibold",children:t})]})},f,j,{...b,render:(t,a,i)=>e.jsx("span",{"data-testid":`connectivity-status-tag-${a.machineName}-${t}`,children:b.render?.(t,a,i)})},{title:s("machines:responseTime"),dataIndex:"duration",key:"duration",width:120,render:e=>e?e<1e3?`${e}ms`:`${(e/1e3).toFixed(1)}s`:"-"},{...v,render:(t,a,i)=>{if(!t)return v.render?.(t,a,i);const n=v.render?.(t,a,i);return e.jsx(ht,{$isError:"failed"===a.status,children:n})}}];return e.jsx(it,{"data-testid":"connectivity-modal",title:e.jsxs(F,{direction:"horizontal",gap:"sm",align:"center",children:[e.jsx(Ie,{}),e.jsx("span",{children:s("machines:connectivityTest")})]}),open:t,onCancel:i,className:I.Large,destroyOnClose:!0,footer:e.jsxs(D,{children:[e.jsx(R,{icon:e.jsx(Re,{}),onClick:async()=>{m(!0);for(let a=0;a<n.length;a++)h(a),d(Math.round(a/n.length*100)),await y(n[a],a);d(100),m(!1),h(-1);const e=r.filter(e=>"success"===e.status).length,t=r.filter(e=>"failed"===e.status).length;0===t?O("success",s("machines:allMachinesConnected",{count:e})):O("warning",s("machines:machinesConnectedWithFailures",{successCount:e,failedCount:t}))},disabled:c||0===n.length,loading:c,"data-testid":"connectivity-run-test-button",children:s(c?"machines:testing":"machines:runTest")}),e.jsx(E,{title:"Close",children:e.jsx(R,{iconOnly:!0,icon:e.jsx(De,{}),onClick:i,"data-testid":"connectivity-close-button","aria-label":"Close"})})]}),children:e.jsx(nt,{children:e.jsxs(T,{children:[c&&e.jsxs(st,{"data-testid":"connectivity-progress-container",children:[e.jsx(rt,{percent:l,status:"active","data-testid":"connectivity-progress-bar"}),u>=0&&u<n.length&&e.jsx(w,{size:"xs",color:"secondary","data-testid":"connectivity-progress-text",children:s("machines:testingMachine",{machineName:n[u].machineName})})]}),e.jsx(pt,{children:e.jsx(A,{message:s("machines:connectivityTestDescription"),variant:"info",showIcon:!0,icon:e.jsx(Ie,{}),"data-testid":"connectivity-info-alert"})}),e.jsx(dt,{children:e.jsx(we,{columns:N,dataSource:r,rowKey:"machineName",pagination:!1,scroll:{y:400},loading:0===n.length,rowClassName:e=>`status-${e.status}`,"data-testid":"connectivity-results-table"})}),!c&&r.some(e=>"pending"!==e.status)&&e.jsx(ot,{"data-testid":"connectivity-summary-statistics",children:e.jsxs(ct,{children:[e.jsxs(mt,{"data-testid":"connectivity-total-machines",children:[e.jsxs(w,{color:"secondary",children:[s("machines:totalMachines"),":"]}),e.jsx(lt,{children:n.length})]}),e.jsxs(mt,{"data-testid":"connectivity-connected-count",children:[e.jsxs(w,{color:"secondary",children:[s("machines:connected"),":"]}),e.jsx(lt,{$variant:"success",children:r.filter(e=>"success"===e.status).length})]}),e.jsxs(mt,{"data-testid":"connectivity-failed-count",children:[e.jsxs(w,{color:"secondary",children:[s("machines:failed"),":"]}),e.jsx(lt,{$variant:"error",children:r.filter(e=>"failed"===e.status).length})]}),e.jsxs(mt,{"data-testid":"connectivity-average-response",children:[e.jsxs(w,{color:"secondary",children:[s("machines:averageResponse"),":"]}),e.jsx(lt,{children:(()=>{const e=r.filter(e=>"success"===e.status&&e.duration);if(0===e.length)return"-";const t=e.reduce((e,t)=>e+(t.duration||0),0)/e.length;return t<1e3?`${Math.round(t)}ms`:`${(t/1e3).toFixed(1)}s`})()})]})]})})]})})})},xt=(e,t={})=>{const{rowHeight:i=54,headerHeight:n=55,paginationHeight:s=64,containerOffset:r=32,minRows:o=5,maxRows:c=100}=t,[m,l]=a.useState(10),d=a.useRef(null),u=a.useCallback(()=>{if(!e.current)return;const t=e.current.offsetHeight-n-s-r,a=Math.floor(t/i),m=Math.max(o,Math.min(c,a));l(m)},[e,i,n,s,r,o,c]),h=a.useRef(null);return a.useEffect(()=>(h.current=((e,t=300)=>{let a=null;const i=()=>{a&&clearTimeout(a),a=setTimeout(()=>{e()},t)};return i.cancel=()=>{a&&(clearTimeout(a),a=null)},i})(u,300),()=>{h.current?.cancel()}),[u]),a.useEffect(()=>(u(),e.current&&window.ResizeObserver&&(d.current=new ResizeObserver(()=>{h.current?.()}),d.current.observe(e.current)),()=>{d.current&&d.current.disconnect(),h.current?.cancel()}),[u,e]),m},yt=f(N).attrs({$gap:"MD"})`
  height: 100%;

  /* Custom selection state - RediaccTable handles hover via interactive prop */
  .machine-table-row--selected td {
    background-color: var(--color-bg-selected);
  }
`,ft=f.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
`,jt=f.div`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
  padding: ${({theme:e})=>e.spacing.SM}px ${({theme:e})=>e.spacing.MD}px;
  background-color: var(--color-bg-secondary);
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border: 1px solid var(--color-border-secondary);
  gap: ${({theme:e})=>e.spacing.MD}px;
`,bt=f.span`
  font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
  color: var(--color-text-primary);
`,vt=f.div`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
`,Nt=f(R)`
  && {
    min-width: 42px;
  }
`,kt=f.span`
  width: 1px;
  height: ${({theme:e})=>e.spacing.LG}px;
  background-color: var(--color-border-secondary);
  margin: 0 ${({theme:e})=>e.spacing.SM}px;
`,Ct=f.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XL}px;
`,wt=f(z)`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.LG}px;
    border: 2px solid ${({$isAlternate:e})=>e?"var(--color-border-primary)":"var(--color-border-secondary)"};
    box-shadow: ${({theme:e})=>e.shadows.CARD};
    background-color: ${({$isAlternate:e})=>e?"var(--color-bg-secondary)":"var(--color-bg-primary)"};
  }

  .ant-card-head {
    background-color: ${({$isAlternate:e})=>e?"var(--color-bg-hover)":"var(--color-bg-primary)"};
    border-bottom: 2px solid ${({$isAlternate:e})=>e?"var(--color-border-primary)":"var(--color-border-secondary)"};
  }

  .ant-card-body {
    padding: 0;
    background-color: ${({$isAlternate:e})=>e?"var(--color-bg-hover)":"var(--color-bg-primary)"};
  }
`,$t=f(S)`
  padding: ${({theme:e})=>e.spacing.XS}px 0;
`,St=f.div`
  width: ${({theme:e})=>e.spacing.XS}px;
  height: ${L.DIMENSIONS.ICON_XL}px;
  border-radius: ${({theme:e})=>e.borderRadius.SM}px;
  background-color: ${({$color:e})=>e||"var(--color-text-secondary)"};
`,Mt=f.span`
  font-size: ${({theme:e})=>e.fontSize.LG}px;
  font-weight: ${({theme:e})=>e.fontWeight.BOLD};
  color: var(--color-text-primary);
`,It=f.span`
  font-size: ${({theme:e})=>e.fontSize.SM}px;
  color: var(--color-text-secondary);
`,Tt=f.div`
  padding: ${({theme:e})=>`${e.spacing.MD}px ${e.spacing.LG}px`};
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid var(--color-border-secondary);
  background-color: ${({$isStriped:e})=>e?"var(--color-bg-tertiary)":"transparent"};
  cursor: pointer;
  transition: background-color 0.2s ease;

  &:hover {
    background-color: var(--color-bg-hover);
  }

  &:last-child {
    border-bottom: none;
  }
`,At=f.div`
  display: flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.LG}px;
`,Dt=f(G)`
  font-size: ${L.DIMENSIONS.ICON_MD}px;
  color: var(--color-primary);
`,Rt=f(Dt)`
  font-size: ${L.DIMENSIONS.ICON_LG}px;
`,Et=f.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XS}px;
`,Ft=f.span`
  font-size: ${({theme:e})=>e.fontSize.MD}px;
  font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
  color: var(--color-text-primary);
`,Vt=f(R)`
  && {
    /* Maintain compact pill styling to mirror historical control surface */
    gap: ${({theme:e})=>e.spacing.XS}px;
  }
`,Pt=f($).attrs(({$preset:e,$variant:t})=>({preset:e||t,borderless:!0}))``,Ot=f($).attrs(({$preset:e,$variant:t})=>({preset:e||t,borderless:!0,size:"md"}))`
  && {
    font-size: ${({theme:e})=>e.fontSize.MD}px;
    padding: ${({theme:e})=>e.spacing.XS}px ${({theme:e})=>e.spacing.MD}px;
  }
`,Lt=f(W)`
  && .ant-badge-count {
    background-color: ${({$isPositive:e})=>e?"var(--color-success)":"var(--color-border-secondary)"};
    color: ${({$isPositive:e})=>e?"var(--color-text-inverse)":"var(--color-text-secondary)"};
  }
`,zt=f.div`
  margin-top: ${({theme:e})=>2*e.spacing.XXL}px;
`,Gt=({teamFilter:s,showActions:c=!0,className:m="",onEditMachine:l,onFunctionsMachine:d,onDeleteMachine:u,enabled:p=!0,onQueueItemCreated:g,onRowClick:x,selectedMachine:y})=>{const{t:f}=Ee(["machines","common","functions","resources"]),j=i(),b=t(e=>e.ui.uiMode),v="expert"===b,{executePingForMachineAndWait:N}=tt(),k=a.useRef(null),[C,w]=a.useState("machine"),[$,S]=a.useState([]),M=X(),I=q(),T=q(),[A,D]=a.useState(!1),[F,P]=a.useState(!1),[z,W]=a.useState(!1),[ae,ie]=a.useState(null),[ne,se]=a.useState(!1);n.useEffect(()=>{"simple"===b&&"machine"!==C&&w("machine")},[b,C]);const{data:re=[],isLoading:oe,refetch:ce}=r(s,p),{data:me=[]}=o(s),le=xt(k,{containerOffset:170,minRows:5,maxRows:50}),de=re,ue=a.useCallback(e=>Be(e,me.map(e=>({repositoryGuid:e.repositoryGuid,repositoryName:e.repositoryName,grandGuid:e.grandGuid}))),[me]),ge=a.useCallback(e=>{u&&u(e)},[u]),xe=a.useCallback(e=>{x?x(e):(ie(e),se(!0))},[x]),ye=a.useCallback(()=>{se(!1),ie(null)},[]),{getFunctionsByCategory:fe}=h(),je=a.useMemo(()=>fe("machine").filter(e=>e&&!1!==e.showInMenu&&"mount"!==e.name&&"pull"!==e.name),[fe]),ve=v&&U.isEnabled("assignToCluster"),$e=a.useCallback(e=>{e.open&&e.machine?T.open(e.machine):T.close()},[T]),Se=a.useCallback(e=>{e.open&&e.entityType&&e.entityIdentifier?M.open({entityType:e.entityType,entityIdentifier:e.entityIdentifier,entityName:e.entityName}):M.close()},[M]),Me=n.useMemo(()=>(({t:t,isExpertMode:a,uiMode:i,showActions:n,hasSplitView:s,canAssignToCluster:r,onEditMachine:o,onFunctionsMachine:c,handleDelete:m,handleRowClick:l,executePingForMachineAndWait:d,setAssignClusterModal:u,setAuditTraceModal:h,machineFunctions:p})=>{const g=[],x=Ne({title:t("machines:machineName"),dataIndex:"machineName",key:"machineName",maxLength:50,sorter:He("machineName"),renderWrapper:t=>e.jsxs(he,{children:[e.jsx(Dt,{}),e.jsx("strong",{children:t})]})});return g.push(ke({title:t("machines:status"),dataIndex:"vaultStatusTime",key:"status",statusMap:{online:{icon:e.jsx(V,{}),label:t("machines:connected"),color:"success"},offline:{icon:e.jsx(Xe,{}),label:t("machines:connectionFailed"),color:"error"},unknown:{icon:e.jsx(Xe,{}),label:t("machines:statusUnknown"),color:"default"}},sorter:Ke(e=>{if(!e.vaultStatusTime)return 1/0;const t=new Date(e.vaultStatusTime+"Z");return((new Date).getTime()-t.getTime())/6e4<=3?0:1}),renderValue:(e,t)=>{if(!t.vaultStatusTime)return"unknown";const a=new Date(t.vaultStatusTime+"Z");return((new Date).getTime()-a.getTime())/6e4<=3?"online":"offline"}}),x),s||g.push(Ne({title:t("machines:team"),dataIndex:"teamName",key:"teamName",width:150,sorter:He("teamName"),renderWrapper:t=>e.jsx(Pt,{$variant:"team",children:t})})),s||(a?g.push(Ne({title:t("machines:region"),dataIndex:"regionName",key:"regionName",width:150,sorter:He("regionName"),renderText:e=>e||"-",renderWrapper:(t,a)=>"-"===a?e.jsx("span",{children:"-"}):e.jsx(Pt,{$variant:"region",children:t})}),Ne({title:t("machines:bridge"),dataIndex:"bridgeName",key:"bridgeName",width:150,sorter:He("bridgeName"),renderWrapper:t=>e.jsx(Pt,{$variant:"bridge",children:t})})):"simple"!==i&&g.push(Ne({title:t("bridges.bridge"),dataIndex:"bridgeName",key:"bridgeName",width:150,sorter:He("bridgeName"),renderWrapper:t=>e.jsx(Pt,{$variant:"bridge",children:t})}))),!s&&r&&g.push({title:t("machines:assignmentStatus.title"),key:"assignmentStatus",width:180,ellipsis:!0,render:(t,a)=>e.jsx(ze,{machine:a})}),s||g.push({title:t("machines:queueItems"),dataIndex:"queueCount",key:"queueCount",width:100,align:"center",sorter:He("queueCount"),render:t=>e.jsx(Lt,{$isPositive:t>0,count:t,showZero:!0})}),n&&g.push(Ce({title:t("common:table.actions"),width:L.DIMENSIONS.CARD_WIDTH,renderActions:a=>e.jsx(be,{buttons:[{type:"view",icon:e.jsx(qe,{}),tooltip:"common:viewDetails",onClick:()=>l(a),variant:"default",testIdSuffix:"view-details"},{type:"edit",icon:e.jsx(Ze,{}),tooltip:"common:actions.edit",onClick:()=>o?.(a)},{type:"remote",icon:e.jsx(Je,{}),tooltip:"machines:remote",dropdownItems:[{key:"functions",label:t("machines:runAction"),icon:e.jsx(Je,{}),children:[...p.filter(e=>!1!==e?.showInMenu).map(t=>({key:`function-${t?.name||"unknown"}`,label:e.jsx("span",{title:t?.description||"",children:t?.name||"Unknown"}),onClick:()=>c?.(a,t?.name)})),{type:"divider"},{key:"advanced",label:t("machines:advanced"),icon:e.jsx(Je,{}),onClick:()=>c?.(a)}]},{key:"test",label:t("machines:connectivityTest"),icon:e.jsx(Ie,{}),onClick:async()=>{O("info",t("machines:testingConnection"));const e=await d(a,{priority:4,description:"Connectivity test",addedVia:"machine-table",timeout:15e3});e.success?O("success",t("machines:connectionSuccessful")):O("error",e.error||t("machines:connectionFailed"))}},...r?[{key:"assignCluster",label:a.cephClusterName?t("machines:changeClusterAssignment"):t("machines:assignToCluster"),icon:e.jsx(_,{}),onClick:()=>u({open:!0,machine:a})}]:[]]},{type:"trace",icon:e.jsx(B,{}),tooltip:"machines:trace",onClick:()=>h({open:!0,entityType:"Machine",entityIdentifier:a.machineName,entityName:a.machineName})},{type:"delete",icon:e.jsx(Q,{}),tooltip:"common:actions.delete",onClick:()=>m(a),danger:!0},{type:"custom",render:t=>e.jsx(Ue,{machine:t.machineName,teamName:t.teamName})}],record:a,idField:"machineName",testIdPrefix:"machine",t:t})})),g})({t:f,isExpertMode:v,uiMode:b,showActions:c,hasSplitView:Boolean(x),canAssignToCluster:ve,onEditMachine:l,onFunctionsMachine:d,handleDelete:ge,handleRowClick:xe,executePingForMachineAndWait:N,setAssignClusterModal:$e,setAuditTraceModal:Se,machineFunctions:je}),[f,v,b,c,x,ve,l,d,ge,xe,N,$e,Se,je]),Te=ve?{selectedRowKeys:$,onChange:e=>{S(e)},getCheckboxProps:e=>({disabled:!1,"data-testid":`machine-checkbox-${e.machineName}`})}:void 0,De=a.useMemo(()=>{const e={};return"machine"===C||de.forEach(t=>{let a="";if("bridge"===C)a=t.bridgeName;else if("team"===C)a=t.teamName;else if("region"===C)a=t.regionName||"Unknown";else{if("repository"===C){const a=ue(t);if(0===a.length)return;return void a.forEach(a=>{const i=a.name;e[i]||(e[i]=[]),e[i].find(e=>e.machineName===t.machineName)||e[i].push(t)})}if("status"===C){const e=ue(t);if(0===e.length)a="No Repositories";else{const t=e.some(e=>!e.accessible),i=e.some(e=>e.mounted&&e.docker_running),n=e.some(e=>e.mounted&&!e.docker_running),s=e.some(e=>!e.mounted);a=t?"Inaccessible":i?"Active (Running)":n?"Ready (Stopped)":s?"Not Mounted":"Unknown Status"}}else if("grand"===C){const a=ue(t);if(0===a.length)return;return void a.forEach(a=>{let i="No Grand Repository";if(a.grandGuid){const e=me.find(e=>e.repositoryGuid===a.grandGuid);e&&(i=e.repositoryName)}e[i]||(e[i]=[]),e[i].find(e=>e.machineName===t.machineName)||e[i].push(t)})}}a&&(e[a]||(e[a]=[]),e[a].push(t))}),e},[de,C,me,ue]);return e.jsxs(yt,{className:m,children:["simple"===b?null:e.jsx(vt,{children:e.jsxs(he,{wrap:!0,size:"small",children:[e.jsx(E,{title:f("machines:machine"),children:e.jsx(Nt,{variant:"machine"===C?"primary":"default",icon:e.jsx(G,{}),onClick:()=>w("machine"),"data-testid":"machine-view-toggle-machine","aria-label":f("machines:machine")})}),e.jsx(kt,{}),e.jsx(E,{title:f("machines:groupByBridge"),children:e.jsx(Nt,{variant:"bridge"===C?"primary":"default",icon:e.jsx(_,{}),onClick:()=>w("bridge"),"data-testid":"machine-view-toggle-bridge","aria-label":f("machines:groupByBridge")})}),e.jsx(E,{title:f("machines:groupByTeam"),children:e.jsx(Nt,{variant:"team"===C?"primary":"default",icon:e.jsx(H,{}),onClick:()=>w("team"),"data-testid":"machine-view-toggle-team","aria-label":f("machines:groupByTeam")})}),v&&e.jsx(E,{title:f("machines:groupByRegion"),children:e.jsx(Nt,{variant:"region"===C?"primary":"default",icon:e.jsx(K,{}),onClick:()=>w("region"),"data-testid":"machine-view-toggle-region","aria-label":f("machines:groupByRegion")})}),e.jsx(E,{title:f("machines:groupByRepo"),children:e.jsx(Nt,{variant:"repository"===C?"primary":"default",icon:e.jsx(Z,{}),onClick:()=>w("repository"),"data-testid":"machine-view-toggle-repo","aria-label":f("machines:groupByRepo")})}),e.jsx(E,{title:f("machines:groupByStatus"),children:e.jsx(Nt,{variant:"status"===C?"primary":"default",icon:e.jsx(J,{}),onClick:()=>w("status"),"data-testid":"machine-view-toggle-status","aria-label":f("machines:groupByStatus")})}),e.jsx(E,{title:f("machines:groupByGrand"),children:e.jsx(Nt,{variant:"grand"===C?"primary":"default",icon:e.jsx(Qe,{}),onClick:()=>w("grand"),"data-testid":"machine-view-toggle-grand","aria-label":f("machines:groupByGrand")})})]})}),ve&&0!==$.length?e.jsxs(jt,{children:[e.jsxs(he,{size:"middle",children:[e.jsx(bt,{children:f("machines:bulkActions.selected",{count:$.length})}),e.jsx(E,{title:f("common:actions.clearSelection"),children:e.jsx(R,{onClick:()=>S([]),"data-testid":"machine-bulk-clear-selection","aria-label":f("common:actions.clearSelection"),children:"Clear"})})]}),e.jsxs(he,{size:"middle",children:[e.jsx(E,{title:f("machines:bulkActions.assignToCluster"),children:e.jsx(R,{variant:"primary",icon:e.jsx(_,{}),onClick:()=>D(!0),"data-testid":"machine-bulk-assign-cluster","aria-label":f("machines:bulkActions.assignToCluster")})}),e.jsx(E,{title:f("machines:bulkActions.removeFromCluster"),children:e.jsx(R,{icon:e.jsx(_,{}),onClick:()=>P(!0),"data-testid":"machine-bulk-remove-cluster","aria-label":f("machines:bulkActions.removeFromCluster")})}),e.jsx(E,{title:f("machines:bulkActions.viewAssignmentStatus"),children:e.jsx(R,{icon:e.jsx(Y,{}),onClick:()=>W(!0),"data-testid":"machine-bulk-view-status","aria-label":f("machines:bulkActions.viewAssignmentStatus")})})]})]}):null,"machine"===C?e.jsx(ft,{ref:k,children:e.jsx(we,{columns:Me,dataSource:de,rowKey:"machineName",loading:oe,interactive:!0,selectable:!0,scroll:{x:"max-content"},rowSelection:Te,rowClassName:e=>{const t="machine-table-row";return y?.machineName===e.machineName?`${t} machine-table-row--selected`:t},"data-testid":"machine-table",pagination:{pageSize:le,showSizeChanger:!1,showTotal:(e,t)=>f("common:table.showingRecords",{start:t[0],end:t[1],total:e})},onRow:e=>({"data-testid":`machine-row-${e.machineName}`,onClick:t=>{const a=t.target;a.closest("button")||a.closest(".ant-dropdown")||a.closest(".ant-dropdown-menu")||j(`/machines/${e.machineName}/repositories`,{state:{machine:e}})}}),sticky:!0})}):(()=>{if(0===Object.keys(De).length)return e.jsx(zt,{children:e.jsx(ee,{variant:"minimal",image:pe.PRESENTED_IMAGE_SIMPLE,description:f("resources:repositories.noRepositories")})});const t={machine:"repository",bridge:"bridge",team:"team",region:"region",repository:"repository",status:"status",grand:"grand"},a={team:"var(--color-success)",bridge:"var(--color-primary)",region:"var(--color-info)",repository:"var(--color-secondary)",status:"var(--color-warning)",grand:"var(--color-secondary)"},i={bridge:e.jsx(_,{}),team:e.jsx(H,{}),region:e.jsx(K,{}),repository:e.jsx(Z,{}),status:e.jsx(J,{}),grand:e.jsx(Qe,{})};return e.jsx(Ct,{children:Object.entries(De).map(([n,s],r)=>{const o=t[C],c=a[o];return e.jsxs(wt,{$isAlternate:r%2==0,children:[e.jsxs($t,{children:[e.jsx(St,{$color:c}),e.jsxs(he,{size:"small",children:[e.jsxs(Mt,{children:["#",r+1]}),e.jsx(Ot,{$variant:o,icon:i[C],children:n}),e.jsxs(It,{children:[s.length," ",1===s.length?f("machines:machine"):f("machines:machines")]})]})]}),s.map((t,a)=>e.jsxs(Tt,{$isStriped:a%2!=0,onClick:()=>j(`/machines/${t.machineName}/repositories`,{state:{machine:t}}),"data-testid":`grouped-machine-row-${t.machineName}`,children:[e.jsxs(At,{children:[e.jsx(Rt,{}),e.jsxs(Et,{children:[e.jsx(Ft,{children:t.machineName}),e.jsxs(he,{size:"small",children:[e.jsx(Pt,{$variant:"team",children:t.teamName}),t.bridgeName&&e.jsx(Pt,{$variant:"bridge",children:t.bridgeName}),t.regionName&&e.jsx(Pt,{$variant:"region",children:t.regionName})]})]})]}),e.jsx(E,{title:f("machines:viewRepos"),children:e.jsx(Vt,{variant:"primary",icon:e.jsx(te,{}),onClick:e=>{e.stopPropagation(),j(`/machines/${t.machineName}/repositories`,{state:{machine:t}})},children:f("machines:viewRepos")})})]},t.machineName))]},n)})})})(),e.jsx(Fe,{open:M.isOpen,onCancel:M.close,entityType:M.entityType,entityIdentifier:M.entityIdentifier,entityName:M.entityName}),I.state.data&&e.jsx(Ae,{open:I.isOpen,onCancel:I.close,machineName:I.state.data.machineName,teamName:I.state.data.teamName,bridgeName:I.state.data.bridgeName,onQueueItemCreated:g}),T.state.data&&e.jsx(Ge,{open:T.isOpen,machine:T.state.data,onCancel:T.close,onSuccess:()=>{T.close(),ce()}}),e.jsx(Ge,{open:A,machines:re.filter(e=>$.includes(e.machineName)),onCancel:()=>D(!1),onSuccess:()=>{D(!1),S([]),ce()}}),e.jsx(We,{open:F,machines:re.filter(e=>$.includes(e.machineName)),onCancel:()=>P(!1),onSuccess:()=>{P(!1),S([]),ce()}}),e.jsx(_e,{open:z,machines:re.filter(e=>$.includes(e.machineName)),onCancel:()=>W(!1)}),!x&&e.jsx(Ve,{machine:ae,visible:ne,onClose:ye})]})},Wt=f.div`
  display: flex;
  height: 100%;
  width: 100%;
  position: relative;
  overflow: hidden;
`,_t=f.div`
  width: ${({$width:e})=>e};
  height: 100%;
  overflow: auto;
  min-width: ${({theme:e})=>e.dimensions.SPLIT_PANEL_MIN_WIDTH}px;
  transition: width 0.3s ease-in-out;
`,Bt=f.div`
  position: fixed;
  top: 0;
  left: 0;
  right: ${({$rightOffset:e})=>`${e}px`};
  bottom: 0;
  background-color: ${({theme:e})=>e.overlays.backdrop};
  opacity: ${({$visible:e})=>e?1:0};
  transition: opacity 250ms ease-in-out, right 0.3s ease-in-out;
  z-index: ${({theme:e})=>e.zIndex.MODAL};
  pointer-events: ${({$visible:e})=>e?"auto":"none"};
`,Qt=t=>{const{type:i,selectedResource:n,onResourceSelect:s,isPanelCollapsed:r=!0,onTogglePanelCollapse:o}=t,c=Pe(),[m,l]=a.useState(c),[d,u]=a.useState(!1),[h,p]=a.useState(!1);a.useEffect(()=>{l(c)},[c]),a.useEffect(()=>{if(!n){u(!1);const e=setTimeout(()=>{p(!1)},250);return()=>clearTimeout(e)}p(!0),requestAnimationFrame(()=>{u(!0)})},[n]);const g=e=>{s(e)},x=()=>{s(null)},y=r?Oe.COLLAPSED_WIDTH:m;if("machine"===i){const a=n?`calc(100% - ${y}px)`:"100%";return e.jsxs(Wt,{"data-testid":"split-resource-view-container",children:[e.jsx(_t,{$width:a,"data-testid":"split-resource-view-left-panel",children:e.jsx(Gt,{...t,onRowClick:g,selectedMachine:n})}),h&&e.jsx(Bt,{$visible:d,$rightOffset:y,onClick:x,"data-testid":"split-resource-view-backdrop"}),n&&e.jsx(Le,{type:"machineName"in n?"machine":"repositoryName"in n?"repository":"container",data:n,visible:!0,onClose:x,splitWidth:m,onSplitWidthChange:l,isCollapsed:r,onToggleCollapse:o,collapsedWidth:Oe.COLLAPSED_WIDTH})]})}return null},Xt=f(pe)`
  && {
    padding: ${({theme:e})=>e.spacing.LG}px 0;
  }
`,qt=f(xe)`
  && {
    width: 100%;
  }
`,Ut=()=>{const{t:t}=Ee(["resources","machines","common"]),[n,h]=ge.useModal(),f=s(),j=i(),{teams:b,selectedTeams:v,setSelectedTeams:N,isLoading:k}=ye(),{modalState:C,currentResource:w,openModal:$,closeModal:S}=fe("machine"),[M,I]=a.useState(null),[T,A]=a.useState(null),[D,F]=a.useState(null),[V,P]=a.useState(!0),[L,z]=a.useState({}),{state:G,open:W,close:_}=ae(),B=q(),{data:Q=[],refetch:X}=r(v.length>0?v:void 0,v.length>0),{data:U=[]}=o(v.length>0?v:void 0),{data:H=[]}=p(v.length>0?v:void 0),K=c(),Z=m(),J=l(),Y=d(),ee=u(),{executeAction:te,isExecuting:he}=ve();a.useEffect(()=>{const e=f.state;e?.createRepository&&j("/credentials",{state:e,replace:!0})},[f,j]);const pe=e=>{I(e),e&&(A(null),F(null),P(!1))},xe=a.useCallback(e=>{Ye({modal:n,t:t,resourceType:"machine",resourceName:e.machineName,translationNamespace:"machines",onConfirm:()=>Y.mutateAsync({teamName:e.teamName,machineName:e.machineName}),onSuccess:()=>X()})},[Y,n,X,t]),je=a.useCallback(async e=>{try{if("create"===C.mode){const{autoSetup:a,...i}=e;if(await K.mutateAsync(i),O("success",t("machines:createSuccess")),a)try{await new Promise(e=>setTimeout(e,500));const a=await te({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,functionName:"setup",params:{datastore_size:"95%",source:"apt-repo",rclone_source:"install-script",docker_source:"docker-repo",install_amd_driver:"auto",install_nvidia_driver:"auto"},priority:3,addedVia:"machine-creation-auto-setup",machineVault:e.vaultContent||"{}"});a.success&&(a.taskId?(O("info",t("machines:setupQueued")),W(a.taskId,e.machineName)):a.isQueued&&O("info",t("machines:setupQueuedForSubmission")))}catch{O("warning",t("machines:machineCreatedButSetupFailed"))}S(),X()}else if(w){const t=w.machineName,a=e.machineName;a&&a!==t&&await Z.mutateAsync({teamName:w.teamName,currentMachineName:t,newMachineName:a}),e.bridgeName&&e.bridgeName!==w.bridgeName&&await J.mutateAsync({teamName:w.teamName,machineName:a||t,newBridgeName:e.bridgeName});const i=e.vaultContent;i&&i!==w.vaultContent&&await ee.mutateAsync({teamName:w.teamName,machineName:a||t,vaultContent:i,vaultVersion:w.vaultVersion+1}),S(),X()}}catch{}},[S,K,w,te,W,X,t,C.mode,J,Z,ee]),be=a.useCallback(async(e,t)=>{if(w)try{await ee.mutateAsync({teamName:w.teamName,machineName:w.machineName,vaultContent:e,vaultVersion:t}),S(),X()}catch{}},[S,w,X,ee]),Ne=a.useCallback(async e=>{if(w)try{const a=w.machineName,i=w.bridgeName,n=b.find(e=>e.teamName===w.teamName),s="string"==typeof e.params.repository?e.params.repository:void 0,r={teamName:w.teamName,machineName:a,bridgeName:i,functionName:e.function.name,params:e.params,priority:e.priority,addedVia:"machine-table",teamVault:n?.vaultContent||"{}",machineVault:w.vaultContent||"{}",vaultContent:"{}"};if(s){const e=U.find(e=>e.repositoryGuid===s);r.repositoryGuid=e?.repositoryGuid||s,r.vaultContent=e?.vaultContent||"{}"}if("pull"===e.function.name){const t="string"==typeof e.params.sourceType?e.params.sourceType:void 0,a="string"==typeof e.params.from?e.params.from:void 0;if("machine"===t&&a){const e=Q.find(e=>e.machineName===a);e?.vaultContent&&(r.sourceMachineVault=e.vaultContent)}if("storage"===t&&a){const e=H.find(e=>e.storageName===a);e?.vaultContent&&(r.sourceStorageVault=e.vaultContent)}}const o=await te(r);S(),o.success?o.taskId?(O("success",t("machines:queueItemCreated")),W(o.taskId,a)):o.isQueued&&O("info",t("resources:messages.highestPriorityQueued",{resourceType:"machine"})):O("error",o.error||t("resources:errors.failedToCreateQueueItem"))}catch{O("error",t("resources:errors.failedToCreateQueueItem"))}},[S,w,te,Q,W,U,H,t,b]),ke=a.useCallback(async(e,a)=>{const i=g[a];if(!i)return void O("error",t("resources:errors.functionNotFound"));const n={};i.params&&Object.entries(i.params).forEach(([e,t])=>{t.default&&(n[e]=t.default)});const s=b.find(t=>t.teamName===e.teamName),r={teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,functionName:a,params:n,priority:4,addedVia:"machine-table-quick",teamVault:s?.vaultContent||"{}",machineVault:e.vaultContent||"{}",vaultContent:"{}"};try{const a=await te(r);a.success?a.taskId?(O("success",t("machines:queueItemCreated")),W(a.taskId,e.machineName)):a.isQueued&&O("info",t("resources:messages.highestPriorityQueued",{resourceType:"machine"})):O("error",a.error||t("resources:errors.failedToCreateQueueItem")),z(t=>({...t,[e.machineName]:Date.now()}))}catch{O("error",t("resources:errors.failedToCreateQueueItem"))}},[te,W,t,b]),Ce=K.isPending||Z.isPending||J.isPending||he,we=ee.isPending,$e=C.data??w??void 0;return e.jsxs(e.Fragment,{children:[e.jsx(ie,{children:e.jsxs(ne,{children:[e.jsx(se,{level:3,children:t("machines:heading",{defaultValue:"Machines"})}),e.jsxs(re,{children:[e.jsx(ne,{children:e.jsxs(oe,{children:[e.jsx(ce,{children:e.jsx(me,{children:e.jsx(qt,{"data-testid":"machines-team-selector",teams:b,selectedTeams:v,onChange:N,loading:k,placeholder:t("teams.selectTeamToView")})})}),v.length>0&&e.jsxs(le,{children:[e.jsx(E,{title:t("machines:createMachine"),children:e.jsx(R,{iconOnly:!0,icon:e.jsx(de,{}),"data-testid":"machines-create-machine-button",onClick:()=>$("create"),"aria-label":t("machines:createMachine")})}),e.jsx(E,{title:t("machines:connectivityTest"),children:e.jsx(R,{iconOnly:!0,icon:e.jsx(Ie,{}),"data-testid":"machines-connectivity-test-button",onClick:()=>B.open(),disabled:0===Q.length,"aria-label":t("machines:connectivityTest")})}),e.jsx(E,{title:t("common:actions.refresh"),children:e.jsx(R,{iconOnly:!0,icon:e.jsx(et,{}),"data-testid":"machines-refresh-button",onClick:()=>{X(),z(e=>({...e,_global:Date.now()}))},"aria-label":t("common:actions.refresh")})})]})]})}),e.jsx(ue,{children:0===v.length?e.jsx(Xt,{image:Xt.PRESENTED_IMAGE_SIMPLE,description:t("teams.selectTeamPrompt")}):e.jsx(Qt,{type:"machine",teamFilter:v,showFilters:!0,showActions:!0,onCreateMachine:()=>$("create"),onEditMachine:e=>$("edit",e),onVaultMachine:e=>$("vault",e),onFunctionsMachine:(e,t)=>{t?ke(e,t):$("create",e)},onDeleteMachine:xe,enabled:v.length>0,refreshKeys:L,onQueueItemCreated:(e,t)=>{W(e,t)},selectedResource:M||T||D,onResourceSelect:e=>{e&&"machineName"in e?pe(e):e&&"repositoryName"in e?(pe(null),A(e),F(null),P(!1)):e&&"id"in e&&"state"in e?(pe(null),A(null),F(e),P(!1)):(pe(null),A(null),F(null))},isPanelCollapsed:V,onTogglePanelCollapse:()=>{P(e=>!e)}})})]})]})}),e.jsx(x,{"data-testid":"machines-machine-modal",open:C.open,onCancel:S,resourceType:"machine",mode:C.mode,existingData:$e,teamFilter:v.length>0?v:void 0,preselectedFunction:C.preselectedFunction,onSubmit:async e=>{const t=e;await je(t)},onUpdateVault:"edit"===C.mode?be:void 0,onFunctionSubmit:e=>Ne(e),isSubmitting:Ce,isUpdatingVault:we,functionCategories:["machine","backup"],hiddenParams:[],defaultParams:{}}),e.jsx(y,{"data-testid":"machines-queue-trace-modal",taskId:G.taskId,open:G.open,onCancel:()=>{const e=G.machineName;_(),e&&z(t=>({...t,[e]:Date.now()})),X()}}),e.jsx(gt,{"data-testid":"machines-connectivity-test-modal",open:B.isOpen,onClose:B.close,machines:Q,teamFilter:v}),h]})};export{Ut as default};
