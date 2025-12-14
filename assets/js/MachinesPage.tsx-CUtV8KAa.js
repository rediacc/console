import{j as e,g as t}from"./chunk-DH1Qig9d.js";import{b as a,f as i,R as n,u as s}from"./chunk-Dx23Oqz1.js";import{u as r,a as o,b as c,c as m,d as l,e as d,f as u}from"./chunk-cMD3kExq.js";import{u as h,a as p,F as g,U as x}from"./chunk-VjKAA7fZ.js";import{Q as y}from"./chunk-B5oQ39sm.js";import{d as f,z as j,B as b,M as v,F as N,h as k,A as C,c as w,G as $,f as S,I as M,J as I,K as T,N as A,O as D,Q as R,U as E,k as F,o as V,l as P,V as O,X as L,a as z,D as G,i as W,C as _,H as B,Y as Q,Z as X,_ as q,$ as U,T as H,a0 as K,x as Z,a1 as J,y as Y,a2 as ee,a3 as te,a4 as ae,a5 as ie,a6 as ne,a7 as se,a8 as re,a9 as oe,aa as ce,ab as me,ac as le,ad as de,ae as ue}from"../index-BEvUMz1n.js";import{y as he,w as pe,F as ge,E as xe,M as ye}from"./chunk-BRjXT_03.js";import{T as fe,u as je}from"./chunk-BQnIwfR4.js";import{u as be}from"./chunk-C6iGxybb.js";import{u as ve,A as Ne,a as ke}from"./chunk-Hsr1kJw5.js";import{c as Ce,a as we,b as $e}from"./chunk-bcnw_mXo.js";import"./chunk-B14EaQed.js";import{u as Se}from"./chunk-1rL94j0f.js";import{u as Me}from"./chunk-BHs5UPE5.js";import{u as Ie,W as Te}from"./chunk-C258ZUKR.js";import{w as Ae,R as De}from"./chunk-DRJ7Jqm1.js";import{C as Re}from"./chunk-DmynLQbO.js";import{S as Ee}from"./chunk-BfJArTwj.js";import{u as Fe}from"./chunk-DsYhoPUY.js";import{A as Ve}from"./chunk-DDbO8WKq.js";import{M as Pe,u as Oe,D as Le,U as ze}from"./chunk-CICIp33-.js";import{M as Ge,A as We,R as _e,V as Be}from"./chunk-C1tiDp3t.js";import{g as Qe}from"./chunk-GqWjj4O2.js";import"./chunk-D63dSdbK.js";import{B as Xe}from"./chunk-BF2KwqC2.js";import{D as qe,E as Ue,L as He}from"./chunk-yMucbQiD.js";import{c as Ke,a as Ze}from"./chunk-BKxNWyZX.js";import{E as Je}from"./chunk-BslfPSAe.js";import{F as Ye}from"./chunk-CdPbBWyo.js";import{c as et}from"./chunk-1JyLU8-d.js";import{R as tt}from"./chunk-B7O9DEY3.js";import"./chunk-CWN1N_SP.js";import"./chunk-DB6ez0TU.js";import"./chunk-JQ8wCAYE.js";import"./chunk-Dg37maA9.js";import"./chunk-DDaRaurs.js";import"./chunk-CqX51j6y.js";import"./chunk-D9u96he_.js";import"./chunk-BL2sDf4l.js";import"./chunk-Cl7AfCm-.js";import"./chunk-D6ucUHF2.js";import"./chunk-DiEm14UO.js";import"./chunk-DPVObqys.js";import"./chunk-B2DckGkX.js";import"./chunk-CFZUNveI.js";import"./chunk-DbLIQOJX.js";import"./chunk-8RLmnHO1.js";import"./chunk-P6TVQdgE.js";import"./chunk-DhpoEw86.js";import"./chunk-C7Ks1yQ-.js";import"./chunk-DOLqSndO.js";import"./chunk-yhVPGZX_.js";import"./forkTokenService.ts-AfjFrPAj.js";function at(e){const{buildQueueVault:t}=Ie();ve();const i=Se(),{data:n}=Me(),s=a.useCallback(async e=>{try{const a=function(e,t){if(e.teamVault&&"{}"!==e.teamVault)return e.teamVault;const a=t?.find(t=>t.teamName===e.teamName);return a?.vaultContent||"{}"}(e,n),s=await async function(e,t,a){const i=4,n="ping-service",s="{}";return a({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,functionName:"ping",params:{},priority:e.priority||i,addedVia:e.addedVia||n,machineVault:e.machineVault||s,teamVault:t,repositoryVault:e.vaultContent||s})}(e,a,t),r=await async function(e,t,a){const i=4,n=await a.mutateAsync({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,queueVault:t,priority:e.priority||i});return s=n,(e=>{if("object"!=typeof e||null===e)return!1;const t=e,a=void 0===t.taskId||"string"==typeof t.taskId,i=void 0===t.isQueued||"boolean"==typeof t.isQueued;return a&&i})(s)?s:{};var s}(e,s,i);return{taskId:r?.taskId,success:!!r?.taskId||!!r?.isQueued}}catch(a){return{success:!1,error:a instanceof Error?a.message:"Failed to execute ping function"}}},[t,i,n]),r=a.useCallback(async(e,t)=>s({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,priority:t?.priority,description:t?.description,addedVia:t?.addedVia,machineVault:e.vaultContent||"{}"}),[s]),o=a.useCallback(async(e,t)=>{const a=await s(e);if(!a.success||!a.taskId)return a;const i=await Ae(a.taskId,t);return{...a,completionResult:i,success:i.success,error:i.success?void 0:i.message}},[s]),c=a.useCallback(async(e,t)=>o({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,priority:t?.priority,description:t?.description,addedVia:t?.addedVia,machineVault:e.vaultContent||"{}"},t?.timeout),[o]);return{executePing:s,executePingForMachine:r,executePingAndWait:o,executePingForMachineAndWait:c,waitForQueueItemCompletion:Ae,isLoading:i.isPending}}const it=j`
  0% {
    opacity: 0.65;
  }
  50% {
    opacity: 1;
  }
  100% {
    opacity: 0.65;
  }
`,nt=f(b)`
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
`,st=f(v)`
  width: 100%;
`,rt=f(N).attrs({$gap:"XS"})``,ot=f(k)`
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
`,ct=f.div`
  padding: ${({theme:e})=>e.spacing.MD}px;
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
  background-color: ${({theme:e})=>e.colors.bgSecondary};
`,mt=f(C)`
  gap: ${({theme:e})=>e.spacing.XL}px;
`,lt=f(N).attrs({$gap:"XS"})``,dt=f(w).attrs({weight:"semibold"})`
  && {
    color: ${({theme:e,$variant:t})=>"success"===t?e.colors.success:"error"===t?e.colors.error:e.colors.textPrimary};
  }
`,ut=f($)`
  .status-testing td {
    animation: ${it} ${({theme:e})=>e.transitions.SLOW};
    background-color: ${({theme:e})=>e.colors.primaryBg};
  }

  .status-success td {
    background-color: ${({theme:e})=>e.colors.bgSuccess};
  }

  .status-failed td {
    background-color: ${({theme:e})=>e.colors.bgError};
  }
`,ht=f(S).attrs({variant:"neutral"})`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.MD}px;
  }
`;f(S)`
  && {
    text-transform: capitalize;
  }
`;const pt=f(w)`
  && {
    color: ${({theme:e,$isError:t})=>t?e.colors.error:e.colors.textPrimary};
  }
`,gt=f.div`
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
  font-size: ${({theme:e})=>e.fontSize.SM}px;
`,xt=({open:t,onClose:i,machines:n})=>{const{t:s}=Fe(["machines","common"]),[r,o]=a.useState([]),[c,m]=a.useState(!1),[l,d]=a.useState(0),[u,h]=a.useState(-1),{executePingForMachine:p,waitForQueueItemCompletion:g}=at();a.useEffect(()=>{if(t&&n.length>0){const e=n.map(e=>({machineName:e.machineName,teamName:e.teamName,bridgeName:e.bridgeName,status:"pending"}));o(e),d(0),h(-1)}},[t,n]);const x=e=>e.success?s("machines:connectionSuccessful"):"TIMEOUT"===e.status?s("machines:testTimeout"):e.message||s("machines:connectionFailed"),y=async(e,t)=>{const a=Date.now();o(e=>e.map((e,a)=>a===t?{...e,status:"testing",timestamp:(new Date).toISOString()}:e));try{const i=await p(e,{priority:4,description:"Connectivity test",addedVia:"connectivity-test"});if(!i.success||!i.taskId)throw new Error(i.error||"Failed to create test task");{o(e=>e.map((e,a)=>a===t?{...e,taskId:i.taskId}:e));const e=await g(i.taskId),n=Date.now()-a;o(a=>a.map((a,i)=>i===t?{...a,status:e.success?"success":"failed",message:x(e),duration:n}:a))}}catch(i){const e=i instanceof Error?i.message:"Failed to create test task",n=Date.now()-a;o(a=>a.map((a,i)=>i===t?{...a,status:"failed",message:e,duration:n}:a))}},f=Ce({title:s("machines:team"),dataIndex:"teamName",key:"teamName",renderWrapper:t=>e.jsx(ht,{children:t})}),j=Ce({title:s("machines:bridge"),dataIndex:"bridgeName",key:"bridgeName",renderWrapper:t=>e.jsx(ht,{children:t})}),b=we({title:s("machines:status"),dataIndex:"status",key:"status",width:140,statusMap:{pending:{color:"default",label:s("machines:pending"),icon:e.jsx(P,{})},testing:{color:"blue",label:s("machines:testing"),icon:e.jsx(Ee,{spin:!0})},success:{color:"success",label:s("machines:connected"),icon:e.jsx(V,{})},failed:{color:"error",label:s("machines:failed"),icon:e.jsx(Re,{})}}}),v=Ce({title:s("machines:message"),dataIndex:"message",key:"message",ellipsis:!0,renderText:e=>e||"-"}),N=[{title:s("machines:machineName"),dataIndex:"machineName",key:"machineName",render:(t,a)=>e.jsxs(M,{"data-testid":`connectivity-machine-${t}`,children:[e.jsx(I,{$variant:a.status,children:(()=>{switch(a.status){case"testing":return e.jsx(Ee,{spin:!0,"data-testid":`connectivity-status-icon-testing-${t}`});case"success":return e.jsx(V,{"data-testid":`connectivity-status-icon-success-${t}`});case"failed":return e.jsx(Re,{"data-testid":`connectivity-status-icon-failed-${t}`});default:return e.jsx(P,{"data-testid":`connectivity-status-icon-pending-${t}`})}})()}),e.jsx(w,{weight:"semibold",children:t})]})},f,j,{...b,render:(t,a,i)=>e.jsx("span",{"data-testid":`connectivity-status-tag-${a.machineName}-${t}`,children:b.render?.(t,a,i)})},{title:s("machines:responseTime"),dataIndex:"duration",key:"duration",width:120,render:e=>e?e<1e3?`${e}ms`:`${(e/1e3).toFixed(1)}s`:"-"},{...v,render:(t,a,i)=>{if(!t)return v.render?.(t,a,i);const n=v.render?.(t,a,i);return e.jsx(pt,{$isError:"failed"===a.status,children:n})}}];return e.jsx(nt,{"data-testid":"connectivity-modal",title:e.jsxs(F,{direction:"horizontal",gap:"sm",align:"center",children:[e.jsx(Te,{}),e.jsx("span",{children:s("machines:connectivityTest")})]}),open:t,onCancel:i,className:T.Large,destroyOnClose:!0,footer:e.jsxs(R,{children:[e.jsx(E,{icon:e.jsx(Ee,{}),onClick:async()=>{m(!0);for(let a=0;a<n.length;a++)h(a),d(Math.round(a/n.length*100)),await y(n[a],a);d(100),m(!1),h(-1);const e=r.filter(e=>"success"===e.status).length,t=r.filter(e=>"failed"===e.status).length;0===t?O("success",s("machines:allMachinesConnected",{count:e})):O("warning",s("machines:machinesConnectedWithFailures",{successCount:e,failedCount:t}))},disabled:c||0===n.length,loading:c,"data-testid":"connectivity-run-test-button",children:s(c?"machines:testing":"machines:runTest")}),e.jsx(he,{title:"Close",children:e.jsx(E,{iconOnly:!0,icon:e.jsx(Re,{}),onClick:i,"data-testid":"connectivity-close-button","aria-label":"Close"})})]}),children:e.jsx(st,{children:e.jsxs(A,{children:[c&&e.jsxs(rt,{"data-testid":"connectivity-progress-container",children:[e.jsx(ot,{percent:l,status:"active","data-testid":"connectivity-progress-bar"}),u>=0&&u<n.length&&e.jsx(w,{size:"xs",color:"secondary","data-testid":"connectivity-progress-text",children:s("machines:testingMachine",{machineName:n[u].machineName})})]}),e.jsx(gt,{children:e.jsx(D,{message:s("machines:connectivityTestDescription"),variant:"info",showIcon:!0,icon:e.jsx(Te,{}),"data-testid":"connectivity-info-alert"})}),e.jsx(ut,{columns:N,dataSource:r,rowKey:"machineName",pagination:!1,scroll:{y:400},loading:0===n.length,rowClassName:e=>`status-${e.status}`,"data-testid":"connectivity-results-table"}),!c&&r.some(e=>"pending"!==e.status)&&e.jsx(ct,{"data-testid":"connectivity-summary-statistics",children:e.jsxs(mt,{children:[e.jsxs(lt,{"data-testid":"connectivity-total-machines",children:[e.jsxs(w,{color:"secondary",children:[s("machines:totalMachines"),":"]}),e.jsx(dt,{children:n.length})]}),e.jsxs(lt,{"data-testid":"connectivity-connected-count",children:[e.jsxs(w,{color:"secondary",children:[s("machines:connected"),":"]}),e.jsx(dt,{$variant:"success",children:r.filter(e=>"success"===e.status).length})]}),e.jsxs(lt,{"data-testid":"connectivity-failed-count",children:[e.jsxs(w,{color:"secondary",children:[s("machines:failed"),":"]}),e.jsx(dt,{$variant:"error",children:r.filter(e=>"failed"===e.status).length})]}),e.jsxs(lt,{"data-testid":"connectivity-average-response",children:[e.jsxs(w,{color:"secondary",children:[s("machines:averageResponse"),":"]}),e.jsx(dt,{children:(()=>{const e=r.filter(e=>"success"===e.status&&e.duration);if(0===e.length)return"-";const t=e.reduce((e,t)=>e+(t.duration||0),0)/e.length;return t<1e3?`${Math.round(t)}ms`:`${(t/1e3).toFixed(1)}s`})()})]})]})})]})})})},yt=(e,t={})=>{const{rowHeight:i=54,headerHeight:n=55,paginationHeight:s=64,containerOffset:r=32,minRows:o=5,maxRows:c=100}=t,[m,l]=a.useState(10),d=a.useRef(null),u=a.useCallback(()=>{if(!e.current)return;const t=e.current.offsetHeight-n-s-r,a=Math.floor(t/i),m=Math.max(o,Math.min(c,a));l(m)},[e,i,n,s,r,o,c]),h=a.useRef(null);return a.useEffect(()=>(h.current=((e,t=300)=>{let a=null;const i=()=>{a&&clearTimeout(a),a=setTimeout(()=>{e()},t)};return i.cancel=()=>{a&&(clearTimeout(a),a=null)},i})(u,300),()=>{h.current?.cancel()}),[u]),a.useEffect(()=>(u(),e.current&&window.ResizeObserver&&(d.current=new ResizeObserver(()=>{h.current?.()}),d.current.observe(e.current)),()=>{d.current&&d.current.disconnect(),h.current?.cancel()}),[u,e]),m},ft=f(N).attrs({$gap:"MD"})`
  height: 100%;

  .machine-table-row {
    cursor: pointer;
    transition: background-color 0.2s ease;
  }

  .machine-table-row:hover {
    background-color: var(--color-bg-hover);
  }

  .machine-table-row--selected td {
    background-color: var(--color-bg-selected);
  }
`,jt=f.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
`,bt=f.div`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
  padding: ${({theme:e})=>e.spacing.SM}px ${({theme:e})=>e.spacing.MD}px;
  background-color: var(--color-bg-secondary);
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border: 1px solid var(--color-border-secondary);
  gap: ${({theme:e})=>e.spacing.MD}px;
`,vt=f.span`
  font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
  color: var(--color-text-primary);
`,Nt=f.div`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
`,kt=f(E)`
  && {
    min-width: 42px;
  }
`,Ct=f.span`
  width: 1px;
  height: ${({theme:e})=>e.spacing.LG}px;
  background-color: var(--color-border-secondary);
  margin: 0 ${({theme:e})=>e.spacing.SM}px;
`,wt=f.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XL}px;
`,$t=f(z)`
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
`,St=f(M)`
  padding: ${({theme:e})=>e.spacing.XS}px 0;
`,Mt=f.div`
  width: ${({theme:e})=>e.spacing.XS}px;
  height: ${L.DIMENSIONS.ICON_XL}px;
  border-radius: ${({theme:e})=>e.borderRadius.SM}px;
  background-color: ${({$color:e})=>e||"var(--color-text-secondary)"};
`,It=f.span`
  font-size: ${({theme:e})=>e.fontSize.LG}px;
  font-weight: ${({theme:e})=>e.fontWeight.BOLD};
  color: var(--color-text-primary);
`,Tt=f.span`
  font-size: ${({theme:e})=>e.fontSize.SM}px;
  color: var(--color-text-secondary);
`,At=f.div`
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
`,Dt=f.div`
  display: flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.LG}px;
`,Rt=f(G)`
  font-size: ${L.DIMENSIONS.ICON_MD}px;
  color: var(--color-primary);
`,Et=f(Rt)`
  font-size: ${L.DIMENSIONS.ICON_LG}px;
`,Ft=f.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XS}px;
`,Vt=f.span`
  font-size: ${({theme:e})=>e.fontSize.MD}px;
  font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
  color: var(--color-text-primary);
`,Pt=f(E)`
  && {
    /* Maintain compact pill styling to mirror historical control surface */
    gap: ${({theme:e})=>e.spacing.XS}px;
  }
`,Ot=f(S).attrs(({$preset:e,$variant:t})=>({preset:e||t,borderless:!0}))``,Lt=f(S).attrs(({$preset:e,$variant:t})=>({preset:e||t,borderless:!0,size:"md"}))`
  && {
    font-size: ${({theme:e})=>e.fontSize.MD}px;
    padding: ${({theme:e})=>e.spacing.XS}px ${({theme:e})=>e.spacing.MD}px;
  }
`,zt=f(W)`
  && .ant-badge-count {
    background-color: ${({$isPositive:e})=>e?"var(--color-success)":"var(--color-border-secondary)"};
    color: ${({$isPositive:e})=>e?"var(--color-text-inverse)":"var(--color-text-secondary)"};
  }
`,Gt=f.div`
  margin-top: ${({theme:e})=>2*e.spacing.XXL}px;
`,Wt=({teamFilter:s,showActions:c=!0,className:m="",onEditMachine:l,onFunctionsMachine:d,onDeleteMachine:u,enabled:p=!0,onQueueItemCreated:g,onRowClick:x,selectedMachine:y})=>{const{t:f}=Fe(["machines","common","functions","resources"]),j=i(),b=t(e=>e.ui.uiMode),v="expert"===b,{executePingForMachineAndWait:N}=at(),k=a.useRef(null),[C,w]=a.useState("machine"),[$,S]=a.useState([]),M=X(),I=q(),T=q(),[A,D]=a.useState(!1),[R,F]=a.useState(!1),[P,z]=a.useState(!1),[W,ae]=a.useState(null),[ie,ne]=a.useState(!1);n.useEffect(()=>{"simple"===b&&"machine"!==C&&w("machine")},[b,C]);const{data:se=[],isLoading:re,refetch:oe}=r(s,p),{data:ce=[]}=o(s),me=yt(k,{containerOffset:170,minRows:5,maxRows:50}),le=se,de=a.useCallback(e=>Qe(e,ce.map(e=>({repositoryGuid:e.repositoryGuid,repositoryName:e.repositoryName,grandGuid:e.grandGuid}))),[ce]),ue=a.useCallback(e=>{u&&u(e)},[u]),ye=a.useCallback(e=>{x?x(e):(ae(e),ne(!0))},[x]),fe=a.useCallback(()=>{ne(!1),ae(null)},[]),{getFunctionsByCategory:je}=h(),be=a.useMemo(()=>je("machine").filter(e=>e&&!1!==e.showInMenu&&"mount"!==e.name&&"pull"!==e.name),[je]),ve=v&&U.isEnabled("assignToCluster"),ke=a.useCallback(e=>{e.open&&e.machine?T.open(e.machine):T.close()},[T]),Se=a.useCallback(e=>{e.open&&e.entityType&&e.entityIdentifier?M.open({entityType:e.entityType,entityIdentifier:e.entityIdentifier,entityName:e.entityName}):M.close()},[M]),Me=n.useMemo(()=>(({t:t,isExpertMode:a,uiMode:i,showActions:n,hasSplitView:s,canAssignToCluster:r,onEditMachine:o,onFunctionsMachine:c,handleDelete:m,handleRowClick:l,executePingForMachineAndWait:d,setAssignClusterModal:u,setAuditTraceModal:h,machineFunctions:p})=>{const g=[],x=Ce({title:t("machines:machineName"),dataIndex:"machineName",key:"machineName",maxLength:50,sorter:Ke("machineName"),renderWrapper:t=>e.jsxs(pe,{children:[e.jsx(Rt,{}),e.jsx("strong",{children:t})]})});return g.push(we({title:t("machines:status"),dataIndex:"vaultStatusTime",key:"status",statusMap:{online:{icon:e.jsx(V,{}),label:t("machines:connected"),color:"success"},offline:{icon:e.jsx(qe,{}),label:t("machines:connectionFailed"),color:"error"},unknown:{icon:e.jsx(qe,{}),label:t("machines:statusUnknown"),color:"default"}},sorter:Ze(e=>{if(!e.vaultStatusTime)return 1/0;const t=new Date(e.vaultStatusTime+"Z");return((new Date).getTime()-t.getTime())/6e4<=3?0:1}),renderValue:(e,t)=>{if(!t.vaultStatusTime)return"unknown";const a=new Date(t.vaultStatusTime+"Z");return((new Date).getTime()-a.getTime())/6e4<=3?"online":"offline"}}),x),s||g.push(Ce({title:t("machines:team"),dataIndex:"teamName",key:"teamName",width:150,sorter:Ke("teamName"),renderWrapper:t=>e.jsx(Ot,{$variant:"team",children:t})})),s||(a?g.push(Ce({title:t("machines:region"),dataIndex:"regionName",key:"regionName",width:150,sorter:Ke("regionName"),renderText:e=>e||"-",renderWrapper:(t,a)=>"-"===a?e.jsx("span",{children:"-"}):e.jsx(Ot,{$variant:"region",children:t})}),Ce({title:t("machines:bridge"),dataIndex:"bridgeName",key:"bridgeName",width:150,sorter:Ke("bridgeName"),renderWrapper:t=>e.jsx(Ot,{$variant:"bridge",children:t})})):"simple"!==i&&g.push(Ce({title:t("bridges.bridge"),dataIndex:"bridgeName",key:"bridgeName",width:150,sorter:Ke("bridgeName"),renderWrapper:t=>e.jsx(Ot,{$variant:"bridge",children:t})}))),!s&&r&&g.push({title:t("machines:assignmentStatus.title"),key:"assignmentStatus",width:180,ellipsis:!0,render:(t,a)=>e.jsx(Ge,{machine:a})}),s||g.push({title:t("machines:queueItems"),dataIndex:"queueCount",key:"queueCount",width:100,align:"center",sorter:Ke("queueCount"),render:t=>e.jsx(zt,{$isPositive:t>0,count:t,showZero:!0})}),n&&g.push($e({title:t("common:table.actions"),width:L.DIMENSIONS.CARD_WIDTH,renderActions:a=>e.jsx(Ne,{buttons:[{type:"view",icon:e.jsx(Ue,{}),tooltip:"common:viewDetails",onClick:()=>l(a),variant:"default",testIdSuffix:"view-details"},{type:"edit",icon:e.jsx(Je,{}),tooltip:"common:actions.edit",onClick:()=>o?.(a)},{type:"remote",icon:e.jsx(Ye,{}),tooltip:"machines:remote",dropdownItems:[{key:"functions",label:t("machines:runAction"),icon:e.jsx(Ye,{}),children:[...p.filter(e=>!1!==e?.showInMenu).map(t=>({key:`function-${t?.name||"unknown"}`,label:e.jsx("span",{title:t?.description||"",children:t?.name||"Unknown"}),onClick:()=>c?.(a,t?.name)})),{type:"divider"},{key:"advanced",label:t("machines:advanced"),icon:e.jsx(Ye,{}),onClick:()=>c?.(a)}]},{key:"test",label:t("machines:connectivityTest"),icon:e.jsx(Te,{}),onClick:async()=>{O("info",t("machines:testingConnection"));const e=await d(a,{priority:4,description:"Connectivity test",addedVia:"machine-table",timeout:15e3});e.success?O("success",t("machines:connectionSuccessful")):O("error",e.error||t("machines:connectionFailed"))}},...r?[{key:"assignCluster",label:a.cephClusterName?t("machines:changeClusterAssignment"):t("machines:assignToCluster"),icon:e.jsx(_,{}),onClick:()=>u({open:!0,machine:a})}]:[]]},{type:"trace",icon:e.jsx(B,{}),tooltip:"machines:trace",onClick:()=>h({open:!0,entityType:"Machine",entityIdentifier:a.machineName,entityName:a.machineName})},{type:"delete",icon:e.jsx(Q,{}),tooltip:"common:actions.delete",onClick:()=>m(a),danger:!0},{type:"custom",render:t=>e.jsx(He,{machine:t.machineName,teamName:t.teamName})}],record:a,idField:"machineName",testIdPrefix:"machine",t:t})})),g})({t:f,isExpertMode:v,uiMode:b,showActions:c,hasSplitView:Boolean(x),canAssignToCluster:ve,onEditMachine:l,onFunctionsMachine:d,handleDelete:ue,handleRowClick:ye,executePingForMachineAndWait:N,setAssignClusterModal:ke,setAuditTraceModal:Se,machineFunctions:be}),[f,v,b,c,x,ve,l,d,ue,ye,N,ke,Se,be]),Ie=ve?{selectedRowKeys:$,onChange:e=>{S(e)},getCheckboxProps:e=>({disabled:!1,"data-testid":`machine-checkbox-${e.machineName}`})}:void 0,Ae=a.useMemo(()=>{const e={};return"machine"===C||le.forEach(t=>{let a="";if("bridge"===C)a=t.bridgeName;else if("team"===C)a=t.teamName;else if("region"===C)a=t.regionName||"Unknown";else{if("repository"===C){const a=de(t);if(0===a.length)return;return void a.forEach(a=>{const i=a.name;e[i]||(e[i]=[]),e[i].find(e=>e.machineName===t.machineName)||e[i].push(t)})}if("status"===C){const e=de(t);if(0===e.length)a="No Repositories";else{const t=e.some(e=>!e.accessible),i=e.some(e=>e.mounted&&e.docker_running),n=e.some(e=>e.mounted&&!e.docker_running),s=e.some(e=>!e.mounted);a=t?"Inaccessible":i?"Active (Running)":n?"Ready (Stopped)":s?"Not Mounted":"Unknown Status"}}else if("grand"===C){const a=de(t);if(0===a.length)return;return void a.forEach(a=>{let i="No Grand Repository";if(a.grandGuid){const e=ce.find(e=>e.repositoryGuid===a.grandGuid);e&&(i=e.repositoryName)}e[i]||(e[i]=[]),e[i].find(e=>e.machineName===t.machineName)||e[i].push(t)})}}a&&(e[a]||(e[a]=[]),e[a].push(t))}),e},[le,C,ce,de]);return e.jsxs(ft,{className:m,children:["simple"===b?null:e.jsx(Nt,{children:e.jsxs(pe,{wrap:!0,size:"small",children:[e.jsx(he,{title:f("machines:machine"),children:e.jsx(kt,{variant:"machine"===C?"primary":"default",icon:e.jsx(G,{}),onClick:()=>w("machine"),"data-testid":"machine-view-toggle-machine","aria-label":f("machines:machine")})}),e.jsx(Ct,{}),e.jsx(he,{title:f("machines:groupByBridge"),children:e.jsx(kt,{variant:"bridge"===C?"primary":"default",icon:e.jsx(_,{}),onClick:()=>w("bridge"),"data-testid":"machine-view-toggle-bridge","aria-label":f("machines:groupByBridge")})}),e.jsx(he,{title:f("machines:groupByTeam"),children:e.jsx(kt,{variant:"team"===C?"primary":"default",icon:e.jsx(H,{}),onClick:()=>w("team"),"data-testid":"machine-view-toggle-team","aria-label":f("machines:groupByTeam")})}),v&&e.jsx(he,{title:f("machines:groupByRegion"),children:e.jsx(kt,{variant:"region"===C?"primary":"default",icon:e.jsx(K,{}),onClick:()=>w("region"),"data-testid":"machine-view-toggle-region","aria-label":f("machines:groupByRegion")})}),e.jsx(he,{title:f("machines:groupByRepo"),children:e.jsx(kt,{variant:"repository"===C?"primary":"default",icon:e.jsx(Z,{}),onClick:()=>w("repository"),"data-testid":"machine-view-toggle-repo","aria-label":f("machines:groupByRepo")})}),e.jsx(he,{title:f("machines:groupByStatus"),children:e.jsx(kt,{variant:"status"===C?"primary":"default",icon:e.jsx(J,{}),onClick:()=>w("status"),"data-testid":"machine-view-toggle-status","aria-label":f("machines:groupByStatus")})}),e.jsx(he,{title:f("machines:groupByGrand"),children:e.jsx(kt,{variant:"grand"===C?"primary":"default",icon:e.jsx(Xe,{}),onClick:()=>w("grand"),"data-testid":"machine-view-toggle-grand","aria-label":f("machines:groupByGrand")})})]})}),ve&&0!==$.length?e.jsxs(bt,{children:[e.jsxs(pe,{size:"middle",children:[e.jsx(vt,{children:f("machines:bulkActions.selected",{count:$.length})}),e.jsx(he,{title:f("common:actions.clearSelection"),children:e.jsx(E,{onClick:()=>S([]),"data-testid":"machine-bulk-clear-selection","aria-label":f("common:actions.clearSelection"),children:"Clear"})})]}),e.jsxs(pe,{size:"middle",children:[e.jsx(he,{title:f("machines:bulkActions.assignToCluster"),children:e.jsx(E,{variant:"primary",icon:e.jsx(_,{}),onClick:()=>D(!0),"data-testid":"machine-bulk-assign-cluster","aria-label":f("machines:bulkActions.assignToCluster")})}),e.jsx(he,{title:f("machines:bulkActions.removeFromCluster"),children:e.jsx(E,{icon:e.jsx(_,{}),onClick:()=>F(!0),"data-testid":"machine-bulk-remove-cluster","aria-label":f("machines:bulkActions.removeFromCluster")})}),e.jsx(he,{title:f("machines:bulkActions.viewAssignmentStatus"),children:e.jsx(E,{icon:e.jsx(Y,{}),onClick:()=>z(!0),"data-testid":"machine-bulk-view-status","aria-label":f("machines:bulkActions.viewAssignmentStatus")})})]})]}):null,"machine"===C?e.jsx(jt,{ref:k,children:e.jsx(ge,{columns:Me,dataSource:le,rowKey:"machineName",loading:re,scroll:{x:"max-content"},rowSelection:Ie,rowClassName:e=>{const t="machine-table-row";return y?.machineName===e.machineName?`${t} machine-table-row--selected`:t},"data-testid":"machine-table",pagination:{pageSize:me,showSizeChanger:!1,showTotal:(e,t)=>f("common:table.showingRecords",{start:t[0],end:t[1],total:e})},onRow:e=>({"data-testid":`machine-row-${e.machineName}`,onClick:t=>{const a=t.target;a.closest("button")||a.closest(".ant-dropdown")||a.closest(".ant-dropdown-menu")||j(`/machines/${e.machineName}/repositories`,{state:{machine:e}})}}),sticky:!0})}):(()=>{if(0===Object.keys(Ae).length)return e.jsx(Gt,{children:e.jsx(ee,{variant:"minimal",image:xe.PRESENTED_IMAGE_SIMPLE,description:f("resources:repositories.noRepositories")})});const t={machine:"repository",bridge:"bridge",team:"team",region:"region",repository:"repository",status:"status",grand:"grand"},a={team:"var(--color-success)",bridge:"var(--color-primary)",region:"var(--color-info)",repository:"var(--color-secondary)",status:"var(--color-warning)",grand:"var(--color-secondary)"},i={bridge:e.jsx(_,{}),team:e.jsx(H,{}),region:e.jsx(K,{}),repository:e.jsx(Z,{}),status:e.jsx(J,{}),grand:e.jsx(Xe,{})};return e.jsx(wt,{children:Object.entries(Ae).map(([n,s],r)=>{const o=t[C],c=a[o];return e.jsxs($t,{$isAlternate:r%2==0,children:[e.jsxs(St,{children:[e.jsx(Mt,{$color:c}),e.jsxs(pe,{size:"small",children:[e.jsxs(It,{children:["#",r+1]}),e.jsx(Lt,{$variant:o,icon:i[C],children:n}),e.jsxs(Tt,{children:[s.length," ",1===s.length?f("machines:machine"):f("machines:machines")]})]})]}),s.map((t,a)=>e.jsxs(At,{$isStriped:a%2!=0,onClick:()=>j(`/machines/${t.machineName}/repositories`,{state:{machine:t}}),"data-testid":`grouped-machine-row-${t.machineName}`,children:[e.jsxs(Dt,{children:[e.jsx(Et,{}),e.jsxs(Ft,{children:[e.jsx(Vt,{children:t.machineName}),e.jsxs(pe,{size:"small",children:[e.jsx(Ot,{$variant:"team",children:t.teamName}),t.bridgeName&&e.jsx(Ot,{$variant:"bridge",children:t.bridgeName}),t.regionName&&e.jsx(Ot,{$variant:"region",children:t.regionName})]})]})]}),e.jsx(he,{title:f("machines:viewRepos"),children:e.jsx(Pt,{variant:"primary",icon:e.jsx(te,{}),onClick:e=>{e.stopPropagation(),j(`/machines/${t.machineName}/repositories`,{state:{machine:t}})},children:f("machines:viewRepos")})})]},t.machineName))]},n)})})})(),e.jsx(Ve,{open:M.isOpen,onCancel:M.close,entityType:M.entityType,entityIdentifier:M.entityIdentifier,entityName:M.entityName}),I.state.data&&e.jsx(De,{open:I.isOpen,onCancel:I.close,machineName:I.state.data.machineName,teamName:I.state.data.teamName,bridgeName:I.state.data.bridgeName,onQueueItemCreated:g}),T.state.data&&e.jsx(We,{open:T.isOpen,machine:T.state.data,onCancel:T.close,onSuccess:()=>{T.close(),oe()}}),e.jsx(We,{open:A,machines:se.filter(e=>$.includes(e.machineName)),onCancel:()=>D(!1),onSuccess:()=>{D(!1),S([]),oe()}}),e.jsx(_e,{open:R,machines:se.filter(e=>$.includes(e.machineName)),onCancel:()=>F(!1),onSuccess:()=>{F(!1),S([]),oe()}}),e.jsx(Be,{open:P,machines:se.filter(e=>$.includes(e.machineName)),onCancel:()=>z(!1)}),!x&&e.jsx(Pe,{machine:W,visible:ie,onClose:fe})]})},_t=f.div`
  display: flex;
  height: 100%;
  width: 100%;
  position: relative;
  overflow: hidden;
`,Bt=f.div`
  width: ${({$width:e})=>e};
  height: 100%;
  overflow: auto;
  min-width: ${({theme:e})=>e.dimensions.SPLIT_PANEL_MIN_WIDTH}px;
  transition: width 0.3s ease-in-out;
`,Qt=f.div`
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
`,Xt=t=>{const{type:i,selectedResource:n,onResourceSelect:s,isPanelCollapsed:r=!0,onTogglePanelCollapse:o}=t,c=Oe(),[m,l]=a.useState(c),[d,u]=a.useState(!1),[h,p]=a.useState(!1);a.useEffect(()=>{l(c)},[c]),a.useEffect(()=>{if(!n){u(!1);const e=setTimeout(()=>{p(!1)},250);return()=>clearTimeout(e)}p(!0),requestAnimationFrame(()=>{u(!0)})},[n]);const g=e=>{s(e)},x=()=>{s(null)},y=r?Le.COLLAPSED_WIDTH:m;if("machine"===i){const a=n?`calc(100% - ${y}px)`:"100%";return e.jsxs(_t,{"data-testid":"split-resource-view-container",children:[e.jsx(Bt,{$width:a,"data-testid":"split-resource-view-left-panel",children:e.jsx(Wt,{...t,onRowClick:g,selectedMachine:n})}),h&&e.jsx(Qt,{$visible:d,$rightOffset:y,onClick:x,"data-testid":"split-resource-view-backdrop"}),n&&e.jsx(ze,{type:"machineName"in n?"machine":"repositoryName"in n?"repository":"container",data:n,visible:!0,onClose:x,splitWidth:m,onSplitWidthChange:l,isCollapsed:r,onToggleCollapse:o,collapsedWidth:Le.COLLAPSED_WIDTH})]})}return null},qt=f(xe)`
  && {
    padding: ${({theme:e})=>e.spacing.LG}px 0;
  }
`,Ut=f(fe)`
  && {
    width: 100%;
  }
`,Ht=()=>{const{t:t}=Fe(["resources","machines","common"]),[n,h]=ye.useModal(),f=s(),j=i(),{teams:b,selectedTeams:v,setSelectedTeams:N,isLoading:k}=je(),{modalState:C,currentResource:w,openModal:$,closeModal:S}=be("machine"),[M,I]=a.useState(null),[T,A]=a.useState(null),[D,R]=a.useState(null),[F,V]=a.useState(!0),[P,L]=a.useState({}),{state:z,open:G,close:W}=ae(),_=q(),{data:B=[],refetch:Q}=r(v.length>0?v:void 0,v.length>0),{data:X=[]}=o(v.length>0?v:void 0),{data:U=[]}=p(v.length>0?v:void 0),H=c(),K=m(),Z=l(),J=d(),Y=u(),{executeAction:ee,isExecuting:te}=ke();a.useEffect(()=>{const e=f.state;e?.createRepository&&j("/credentials",{state:e,replace:!0})},[f,j]);const pe=e=>{I(e),e&&(A(null),R(null),V(!1))},ge=a.useCallback(e=>{et({modal:n,t:t,resourceType:"machine",resourceName:e.machineName,translationNamespace:"machines",onConfirm:()=>J.mutateAsync({teamName:e.teamName,machineName:e.machineName}),onSuccess:()=>Q()})},[J,n,Q,t]),xe=a.useCallback(async e=>{try{if("create"===C.mode){const{autoSetup:a,...i}=e;if(await H.mutateAsync(i),O("success",t("machines:createSuccess")),a)try{await new Promise(e=>setTimeout(e,500));const a=await ee({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,functionName:"setup",params:{datastore_size:"95%",source:"apt-repo",rclone_source:"install-script",docker_source:"docker-repo",install_amd_driver:"auto",install_nvidia_driver:"auto"},priority:3,addedVia:"machine-creation-auto-setup",machineVault:e.vaultContent||"{}"});a.success&&(a.taskId?(O("info",t("machines:setupQueued")),G(a.taskId,e.machineName)):a.isQueued&&O("info",t("machines:setupQueuedForSubmission")))}catch{O("warning",t("machines:machineCreatedButSetupFailed"))}S(),Q()}else if(w){const t=w.machineName,a=e.machineName;a&&a!==t&&await K.mutateAsync({teamName:w.teamName,currentMachineName:t,newMachineName:a}),e.bridgeName&&e.bridgeName!==w.bridgeName&&await Z.mutateAsync({teamName:w.teamName,machineName:a||t,newBridgeName:e.bridgeName});const i=e.vaultContent;i&&i!==w.vaultContent&&await Y.mutateAsync({teamName:w.teamName,machineName:a||t,vaultContent:i,vaultVersion:w.vaultVersion+1}),S(),Q()}}catch{}},[S,H,w,ee,G,Q,t,C.mode,Z,K,Y]),fe=a.useCallback(async(e,t)=>{if(w)try{await Y.mutateAsync({teamName:w.teamName,machineName:w.machineName,vaultContent:e,vaultVersion:t}),S(),Q()}catch{}},[S,w,Q,Y]),ve=a.useCallback(async e=>{if(w)try{const a=w.machineName,i=w.bridgeName,n=b.find(e=>e.teamName===w.teamName),s="string"==typeof e.params.repository?e.params.repository:void 0,r={teamName:w.teamName,machineName:a,bridgeName:i,functionName:e.function.name,params:e.params,priority:e.priority,addedVia:"machine-table",teamVault:n?.vaultContent||"{}",machineVault:w.vaultContent||"{}",vaultContent:"{}"};if(s){const e=X.find(e=>e.repositoryGuid===s);r.repositoryGuid=e?.repositoryGuid||s,r.vaultContent=e?.vaultContent||"{}"}if("pull"===e.function.name){const t="string"==typeof e.params.sourceType?e.params.sourceType:void 0,a="string"==typeof e.params.from?e.params.from:void 0;if("machine"===t&&a){const e=B.find(e=>e.machineName===a);e?.vaultContent&&(r.sourceMachineVault=e.vaultContent)}if("storage"===t&&a){const e=U.find(e=>e.storageName===a);e?.vaultContent&&(r.sourceStorageVault=e.vaultContent)}}const o=await ee(r);S(),o.success?o.taskId?(O("success",t("machines:queueItemCreated")),G(o.taskId,a)):o.isQueued&&O("info",t("resources:messages.highestPriorityQueued",{resourceType:"machine"})):O("error",o.error||t("resources:errors.failedToCreateQueueItem"))}catch{O("error",t("resources:errors.failedToCreateQueueItem"))}},[S,w,ee,B,G,X,U,t,b]),Ne=a.useCallback(async(e,a)=>{const i=g[a];if(!i)return void O("error",t("resources:errors.functionNotFound"));const n={};i.params&&Object.entries(i.params).forEach(([e,t])=>{t.default&&(n[e]=t.default)});const s=b.find(t=>t.teamName===e.teamName),r={teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,functionName:a,params:n,priority:4,addedVia:"machine-table-quick",teamVault:s?.vaultContent||"{}",machineVault:e.vaultContent||"{}",vaultContent:"{}"};try{const a=await ee(r);a.success?a.taskId?(O("success",t("machines:queueItemCreated")),G(a.taskId,e.machineName)):a.isQueued&&O("info",t("resources:messages.highestPriorityQueued",{resourceType:"machine"})):O("error",a.error||t("resources:errors.failedToCreateQueueItem")),L(t=>({...t,[e.machineName]:Date.now()}))}catch{O("error",t("resources:errors.failedToCreateQueueItem"))}},[ee,G,t,b]),Ce=H.isPending||K.isPending||Z.isPending||te,we=Y.isPending,$e=C.data??w??void 0;return e.jsxs(e.Fragment,{children:[e.jsx(ie,{children:e.jsxs(ne,{children:[e.jsx(se,{level:3,children:t("machines:heading",{defaultValue:"Machines"})}),e.jsxs(re,{children:[e.jsx(ne,{children:e.jsxs(oe,{children:[e.jsx(ce,{children:e.jsx(me,{children:e.jsx(Ut,{"data-testid":"machines-team-selector",teams:b,selectedTeams:v,onChange:N,loading:k,placeholder:t("teams.selectTeamToView")})})}),v.length>0&&e.jsxs(le,{children:[e.jsx(he,{title:t("machines:createMachine"),children:e.jsx(E,{iconOnly:!0,icon:e.jsx(de,{}),"data-testid":"machines-create-machine-button",onClick:()=>$("create"),"aria-label":t("machines:createMachine")})}),e.jsx(he,{title:t("machines:connectivityTest"),children:e.jsx(E,{iconOnly:!0,icon:e.jsx(Te,{}),"data-testid":"machines-connectivity-test-button",onClick:()=>_.open(),disabled:0===B.length,"aria-label":t("machines:connectivityTest")})}),e.jsx(he,{title:t("common:actions.refresh"),children:e.jsx(E,{iconOnly:!0,icon:e.jsx(tt,{}),"data-testid":"machines-refresh-button",onClick:()=>{Q(),L(e=>({...e,_global:Date.now()}))},"aria-label":t("common:actions.refresh")})})]})]})}),e.jsx(ue,{children:0===v.length?e.jsx(qt,{image:qt.PRESENTED_IMAGE_SIMPLE,description:t("teams.selectTeamPrompt")}):e.jsx(Xt,{type:"machine",teamFilter:v,showFilters:!0,showActions:!0,onCreateMachine:()=>$("create"),onEditMachine:e=>$("edit",e),onVaultMachine:e=>$("vault",e),onFunctionsMachine:(e,t)=>{t?Ne(e,t):$("create",e)},onDeleteMachine:ge,enabled:v.length>0,refreshKeys:P,onQueueItemCreated:(e,t)=>{G(e,t)},selectedResource:M||T||D,onResourceSelect:e=>{e&&"machineName"in e?pe(e):e&&"repositoryName"in e?(pe(null),A(e),R(null),V(!1)):e&&"id"in e&&"state"in e?(pe(null),A(null),R(e),V(!1)):(pe(null),A(null),R(null))},isPanelCollapsed:F,onTogglePanelCollapse:()=>{V(e=>!e)}})})]})]})}),e.jsx(x,{"data-testid":"machines-machine-modal",open:C.open,onCancel:S,resourceType:"machine",mode:C.mode,existingData:$e,teamFilter:v.length>0?v:void 0,preselectedFunction:C.preselectedFunction,onSubmit:async e=>{const t=e;await xe(t)},onUpdateVault:"edit"===C.mode?fe:void 0,onFunctionSubmit:e=>ve(e),isSubmitting:Ce,isUpdatingVault:we,functionCategories:["machine","backup"],hiddenParams:[],defaultParams:{}}),e.jsx(y,{"data-testid":"machines-queue-trace-modal",taskId:z.taskId,open:z.open,onCancel:()=>{const e=z.machineName;W(),e&&L(t=>({...t,[e]:Date.now()})),Q()}}),e.jsx(xt,{"data-testid":"machines-connectivity-test-modal",open:_.isOpen,onClose:_.close,machines:B,teamFilter:v}),h]})};export{Ht as default};
