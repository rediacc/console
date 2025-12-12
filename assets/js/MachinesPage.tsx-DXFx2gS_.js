import{j as e,g as t}from"./chunk-DH1Qig9d.js";import{b as a,f as i,R as s,u as n}from"./chunk-Dx23Oqz1.js";import{u as r,a as o,b as c,c as m,d as l,e as d,f as u}from"./chunk-6tKYRcAX.js";import{u as h,a as p,F as g,U as x}from"./chunk-pcUMMl5_.js";import{Q as y}from"./chunk-y2e7F50n.js";import{d as f,z as j,B as b,M as v,F as N,h as k,A as C,c as w,G as $,f as S,I as M,J as I,K as T,N as A,O as D,Q as E,U as R,k as F,o as V,l as P,V as z,X as O,a as L,D as G,i as W,C as _,H as B,Y as Q,Z as X,_ as q,$ as U,T as H,a0 as K,x as Z,a1 as J,y as Y,a2 as ee,a3 as te,a4 as ae,a5 as ie,a6 as se,a7 as ne,a8 as re,a9 as oe,aa as ce,ab as me,ac as le,ad as de,ae as ue}from"../index-CBjoh7UE.js";import{y as he,w as pe,F as ge,b as xe,E as ye,M as fe}from"./chunk-BRjXT_03.js";import{T as je,u as be}from"./chunk-BO9v745d.js";import{u as ve}from"./chunk-C6iGxybb.js";import{u as Ne,A as ke,a as Ce}from"./chunk--u-NxHu9.js";import{c as we,a as $e,b as Se}from"./chunk-CGNAKPnL.js";import"./chunk-DY6C62bW.js";import{u as Me}from"./chunk-Cgr9PKFN.js";import{u as Ie}from"./chunk-CKDYZSei.js";import{u as Te,W as Ae}from"./chunk-B4VpDF1m.js";import{w as De,R as Ee}from"./chunk-e9wxc8sC.js";import{C as Re}from"./chunk-D56SMHb-.js";import{S as Fe}from"./chunk-BwqQCma9.js";import{u as Ve}from"./chunk-DsYhoPUY.js";import{A as Pe}from"./chunk-DFpfDjj3.js";import{M as ze,u as Oe,D as Le,U as Ge}from"./chunk-DxWYiiLD.js";import{M as We,A as _e,R as Be,V as Qe}from"./chunk-CfqFkXGV.js";import{g as Xe}from"./chunk-GqWjj4O2.js";import"./chunk-D63dSdbK.js";import{B as qe}from"./chunk-M-koEcQE.js";import{D as Ue,E as He,L as Ke}from"./chunk-CsADM4pp.js";import{c as Ze,a as Je}from"./chunk-BKxNWyZX.js";import{E as Ye}from"./chunk-CtOk7pVS.js";import{F as et}from"./chunk-rLSnDJnt.js";import{c as tt}from"./chunk-DfqOzEx_.js";import{R as at}from"./chunk-CoAlwRfP.js";import"./chunk-CWN1N_SP.js";import"./chunk-DB6ez0TU.js";import"./chunk-DNYK5fdv.js";import"./chunk-DDKzpTQy.js";import"./chunk-DDaRaurs.js";import"./chunk-CTBsBUOG.js";import"./chunk-i4yy71wc.js";import"./chunk-C6-MF4ev.js";import"./chunk-Bbf7YxC2.js";import"./chunk-nOL9qIKe.js";import"./chunk-Ck9eraSt.js";import"./chunk-DN32mk9b.js";import"./chunk-BsUDGrzv.js";import"./chunk-BCmEXmIu.js";import"./chunk-Bmf4gvFr.js";import"./chunk-Xeg6Fd6A.js";import"./chunk-nAz8J3c3.js";import"./chunk-DhpoEw86.js";import"./chunk-CwQrHb10.js";import"./chunk-DJGNewVx.js";import"./chunk-yhVPGZX_.js";import"./forkTokenService.ts-C4IYrobw.js";function it(e){const{buildQueueVault:t}=Te();Ne();const i=Me(),{data:s}=Ie(),n=a.useCallback(async e=>{try{const a=function(e,t){if(e.teamVault&&"{}"!==e.teamVault)return e.teamVault;const a=t?.find(t=>t.teamName===e.teamName);return a?.vaultContent||"{}"}(e,s),n=await async function(e,t,a){const i=4,s="ping-service",n="{}";return a({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,functionName:"ping",params:{},priority:e.priority||i,addedVia:e.addedVia||s,machineVault:e.machineVault||n,teamVault:t,repositoryVault:e.vaultContent||n})}(e,a,t),r=await async function(e,t,a){const i=4,s=await a.mutateAsync({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,queueVault:t,priority:e.priority||i});return n=s,(e=>{if("object"!=typeof e||null===e)return!1;const t=e,a=void 0===t.taskId||"string"==typeof t.taskId,i=void 0===t.isQueued||"boolean"==typeof t.isQueued;return a&&i})(n)?n:{};var n}(e,n,i);return{taskId:r?.taskId,success:!!r?.taskId||!!r?.isQueued}}catch(a){return{success:!1,error:a instanceof Error?a.message:"Failed to execute ping function"}}},[t,i,s]),r=a.useCallback(async(e,t)=>n({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,priority:t?.priority,description:t?.description,addedVia:t?.addedVia,machineVault:e.vaultContent||"{}"}),[n]),o=a.useCallback(async(e,t)=>{const a=await n(e);if(!a.success||!a.taskId)return a;const i=await De(a.taskId,t);return{...a,completionResult:i,success:i.success,error:i.success?void 0:i.message}},[n]),c=a.useCallback(async(e,t)=>o({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,priority:t?.priority,description:t?.description,addedVia:t?.addedVia,machineVault:e.vaultContent||"{}"},t?.timeout),[o]);return{executePing:n,executePingForMachine:r,executePingAndWait:o,executePingForMachineAndWait:c,waitForQueueItemCompletion:De,isLoading:i.isPending}}const st=j`
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
`,rt=f(v)`
  width: 100%;
`,ot=f(N).attrs({$gap:"XS"})``,ct=f(k)`
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
`,mt=f.div`
  padding: ${({theme:e})=>e.spacing.MD}px;
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
  background-color: ${({theme:e})=>e.colors.bgSecondary};
`,lt=f(C)`
  gap: ${({theme:e})=>e.spacing.XL}px;
`,dt=f(N).attrs({$gap:"XS"})``,ut=f(w).attrs({weight:"semibold"})`
  && {
    color: ${({theme:e,$variant:t})=>"success"===t?e.colors.success:"error"===t?e.colors.error:e.colors.textPrimary};
  }
`,ht=f($)`
  .status-testing td {
    animation: ${st} ${({theme:e})=>e.transitions.SLOW};
    background-color: ${({theme:e})=>e.colors.primaryBg};
  }

  .status-success td {
    background-color: ${({theme:e})=>e.colors.bgSuccess};
  }

  .status-failed td {
    background-color: ${({theme:e})=>e.colors.bgError};
  }
`,pt=f(S).attrs({variant:"neutral"})`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.MD}px;
  }
`;f(S)`
  && {
    text-transform: capitalize;
  }
`;const gt=f(w)`
  && {
    color: ${({theme:e,$isError:t})=>t?e.colors.error:e.colors.textPrimary};
  }
`,xt=f.div`
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
  font-size: ${({theme:e})=>e.fontSize.SM}px;
`,yt=({open:t,onClose:i,machines:s})=>{const{t:n}=Ve(["machines","common"]),[r,o]=a.useState([]),[c,m]=a.useState(!1),[l,d]=a.useState(0),[u,h]=a.useState(-1),{executePingForMachine:p,waitForQueueItemCompletion:g}=it();a.useEffect(()=>{if(t&&s.length>0){const e=s.map(e=>({machineName:e.machineName,teamName:e.teamName,bridgeName:e.bridgeName,status:"pending"}));o(e),d(0),h(-1)}},[t,s]);const x=e=>e.success?n("machines:connectionSuccessful"):"TIMEOUT"===e.status?n("machines:testTimeout"):e.message||n("machines:connectionFailed"),y=async(e,t)=>{const a=Date.now();o(e=>e.map((e,a)=>a===t?{...e,status:"testing",timestamp:(new Date).toISOString()}:e));try{const i=await p(e,{priority:4,description:"Connectivity test",addedVia:"connectivity-test"});if(!i.success||!i.taskId)throw new Error(i.error||"Failed to create test task");{o(e=>e.map((e,a)=>a===t?{...e,taskId:i.taskId}:e));const e=await g(i.taskId),s=Date.now()-a;o(a=>a.map((a,i)=>i===t?{...a,status:e.success?"success":"failed",message:x(e),duration:s}:a))}}catch(i){const e=i instanceof Error?i.message:"Failed to create test task",s=Date.now()-a;o(a=>a.map((a,i)=>i===t?{...a,status:"failed",message:e,duration:s}:a))}},f=we({title:n("machines:team"),dataIndex:"teamName",key:"teamName",renderWrapper:t=>e.jsx(pt,{children:t})}),j=we({title:n("machines:bridge"),dataIndex:"bridgeName",key:"bridgeName",renderWrapper:t=>e.jsx(pt,{children:t})}),b=$e({title:n("machines:status"),dataIndex:"status",key:"status",width:140,statusMap:{pending:{color:"default",label:n("machines:pending"),icon:e.jsx(P,{})},testing:{color:"blue",label:n("machines:testing"),icon:e.jsx(Fe,{spin:!0})},success:{color:"success",label:n("machines:connected"),icon:e.jsx(V,{})},failed:{color:"error",label:n("machines:failed"),icon:e.jsx(Re,{})}}}),v=we({title:n("machines:message"),dataIndex:"message",key:"message",ellipsis:!0,renderText:e=>e||"-"}),N=[{title:n("machines:machineName"),dataIndex:"machineName",key:"machineName",render:(t,a)=>e.jsxs(M,{"data-testid":`connectivity-machine-${t}`,children:[e.jsx(I,{$variant:a.status,children:(()=>{switch(a.status){case"testing":return e.jsx(Fe,{spin:!0,"data-testid":`connectivity-status-icon-testing-${t}`});case"success":return e.jsx(V,{"data-testid":`connectivity-status-icon-success-${t}`});case"failed":return e.jsx(Re,{"data-testid":`connectivity-status-icon-failed-${t}`});default:return e.jsx(P,{"data-testid":`connectivity-status-icon-pending-${t}`})}})()}),e.jsx(w,{weight:"semibold",children:t})]})},f,j,{...b,render:(t,a,i)=>e.jsx("span",{"data-testid":`connectivity-status-tag-${a.machineName}-${t}`,children:b.render?.(t,a,i)})},{title:n("machines:responseTime"),dataIndex:"duration",key:"duration",width:120,render:e=>e?e<1e3?`${e}ms`:`${(e/1e3).toFixed(1)}s`:"-"},{...v,render:(t,a,i)=>{if(!t)return v.render?.(t,a,i);const s=v.render?.(t,a,i);return e.jsx(gt,{$isError:"failed"===a.status,children:s})}}];return e.jsx(nt,{"data-testid":"connectivity-modal",title:e.jsxs(F,{direction:"horizontal",gap:"sm",align:"center",children:[e.jsx(Ae,{}),e.jsx("span",{children:n("machines:connectivityTest")})]}),open:t,onCancel:i,className:T.ExtraLarge,destroyOnClose:!0,footer:e.jsxs(E,{children:[e.jsx(R,{icon:e.jsx(Fe,{}),onClick:async()=>{m(!0);for(let a=0;a<s.length;a++)h(a),d(Math.round(a/s.length*100)),await y(s[a],a);d(100),m(!1),h(-1);const e=r.filter(e=>"success"===e.status).length,t=r.filter(e=>"failed"===e.status).length;0===t?z("success",n("machines:allMachinesConnected",{count:e})):z("warning",n("machines:machinesConnectedWithFailures",{successCount:e,failedCount:t}))},disabled:c||0===s.length,loading:c,"data-testid":"connectivity-run-test-button",children:n(c?"machines:testing":"machines:runTest")}),e.jsx(he,{title:"Close",children:e.jsx(R,{iconOnly:!0,icon:e.jsx(Re,{}),onClick:i,"data-testid":"connectivity-close-button","aria-label":"Close"})})]}),children:e.jsx(rt,{children:e.jsxs(A,{children:[c&&e.jsxs(ot,{"data-testid":"connectivity-progress-container",children:[e.jsx(ct,{percent:l,status:"active","data-testid":"connectivity-progress-bar"}),u>=0&&u<s.length&&e.jsx(w,{size:"xs",color:"secondary","data-testid":"connectivity-progress-text",children:n("machines:testingMachine",{machineName:s[u].machineName})})]}),e.jsx(xt,{children:e.jsx(D,{message:n("machines:connectivityTestDescription"),variant:"info",showIcon:!0,icon:e.jsx(Ae,{}),"data-testid":"connectivity-info-alert"})}),e.jsx(ht,{columns:N,dataSource:r,rowKey:"machineName",pagination:!1,scroll:{y:400},loading:0===s.length,rowClassName:e=>`status-${e.status}`,"data-testid":"connectivity-results-table"}),!c&&r.some(e=>"pending"!==e.status)&&e.jsx(mt,{"data-testid":"connectivity-summary-statistics",children:e.jsxs(lt,{children:[e.jsxs(dt,{"data-testid":"connectivity-total-machines",children:[e.jsxs(w,{color:"secondary",children:[n("machines:totalMachines"),":"]}),e.jsx(ut,{children:s.length})]}),e.jsxs(dt,{"data-testid":"connectivity-connected-count",children:[e.jsxs(w,{color:"secondary",children:[n("machines:connected"),":"]}),e.jsx(ut,{$variant:"success",children:r.filter(e=>"success"===e.status).length})]}),e.jsxs(dt,{"data-testid":"connectivity-failed-count",children:[e.jsxs(w,{color:"secondary",children:[n("machines:failed"),":"]}),e.jsx(ut,{$variant:"error",children:r.filter(e=>"failed"===e.status).length})]}),e.jsxs(dt,{"data-testid":"connectivity-average-response",children:[e.jsxs(w,{color:"secondary",children:[n("machines:averageResponse"),":"]}),e.jsx(ut,{children:(()=>{const e=r.filter(e=>"success"===e.status&&e.duration);if(0===e.length)return"-";const t=e.reduce((e,t)=>e+(t.duration||0),0)/e.length;return t<1e3?`${Math.round(t)}ms`:`${(t/1e3).toFixed(1)}s`})()})]})]})})]})})})},ft=(e,t={})=>{const{rowHeight:i=54,headerHeight:s=55,paginationHeight:n=64,containerOffset:r=32,minRows:o=5,maxRows:c=100}=t,[m,l]=a.useState(10),d=a.useRef(null),u=a.useCallback(()=>{if(!e.current)return;const t=e.current.offsetHeight-s-n-r,a=Math.floor(t/i),m=Math.max(o,Math.min(c,a));l(m)},[e,i,s,n,r,o,c]),h=a.useRef(null);return a.useEffect(()=>(h.current=((e,t=300)=>{let a=null;const i=()=>{a&&clearTimeout(a),a=setTimeout(()=>{e()},t)};return i.cancel=()=>{a&&(clearTimeout(a),a=null)},i})(u,300),()=>{h.current?.cancel()}),[u]),a.useEffect(()=>(u(),e.current&&window.ResizeObserver&&(d.current=new ResizeObserver(()=>{h.current?.()}),d.current.observe(e.current)),()=>{d.current&&d.current.disconnect(),h.current?.cancel()}),[u,e]),m},jt=f(N).attrs({$gap:"MD"})`
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
`,bt=f.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
`,vt=f.div`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
  padding: ${({theme:e})=>e.spacing.SM}px ${({theme:e})=>e.spacing.MD}px;
  background-color: var(--color-bg-secondary);
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border: 1px solid var(--color-border-secondary);
  gap: ${({theme:e})=>e.spacing.MD}px;
`,Nt=f.span`
  font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
  color: var(--color-text-primary);
`,kt=f.div`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
`,Ct=f(R).attrs({size:"sm"})`
  && {
    min-width: 42px;
  }
`,wt=f.span`
  width: 1px;
  height: ${({theme:e})=>e.spacing.LG}px;
  background-color: var(--color-border-secondary);
  margin: 0 ${({theme:e})=>e.spacing.SM}px;
`,$t=f.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XL}px;
`,St=f(L)`
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
`,Mt=f(M)`
  padding: ${({theme:e})=>e.spacing.XS}px 0;
`,It=f.div`
  width: ${({theme:e})=>e.spacing.XS}px;
  height: ${O.DIMENSIONS.ICON_XL}px;
  border-radius: ${({theme:e})=>e.borderRadius.SM}px;
  background-color: ${({$color:e})=>e||"var(--color-text-secondary)"};
`,Tt=f.span`
  font-size: ${({theme:e})=>e.fontSize.LG}px;
  font-weight: ${({theme:e})=>e.fontWeight.BOLD};
  color: var(--color-text-primary);
`,At=f.span`
  font-size: ${({theme:e})=>e.fontSize.SM}px;
  color: var(--color-text-secondary);
`,Dt=f.div`
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
`,Et=f.div`
  display: flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.LG}px;
`,Rt=f(G)`
  font-size: ${O.DIMENSIONS.ICON_MD}px;
  color: var(--color-primary);
`,Ft=f(Rt)`
  font-size: ${O.DIMENSIONS.ICON_LG}px;
`,Vt=f.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XS}px;
`,Pt=f.span`
  font-size: ${({theme:e})=>e.fontSize.MD}px;
  font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
  color: var(--color-text-primary);
`,zt=f(R).attrs({size:"sm"})`
  && {
    /* Maintain compact pill styling to mirror historical control surface */
    gap: ${({theme:e})=>e.spacing.XS}px;
  }
`,Ot=f(S).attrs(({$preset:e,$variant:t})=>({preset:e||t,borderless:!0}))``,Lt=f(S).attrs(({$preset:e,$variant:t})=>({preset:e||t,borderless:!0,size:"md"}))`
  && {
    font-size: ${({theme:e})=>e.fontSize.MD}px;
    padding: ${({theme:e})=>e.spacing.XS}px ${({theme:e})=>e.spacing.MD}px;
  }
`,Gt=f(W)`
  && .ant-badge-count {
    background-color: ${({$isPositive:e})=>e?"var(--color-success)":"var(--color-border-secondary)"};
    color: ${({$isPositive:e})=>e?"var(--color-text-inverse)":"var(--color-text-secondary)"};
  }
`,Wt=f.div`
  margin-top: ${({theme:e})=>2*e.spacing.XXL}px;
`,_t=({teamFilter:n,showActions:c=!0,className:m="",onEditMachine:l,onFunctionsMachine:d,onDeleteMachine:u,enabled:p=!0,onQueueItemCreated:g,onRowClick:x,selectedMachine:y})=>{const{t:f}=Ve(["machines","common","functions","resources"]),j=i(),b=t(e=>e.ui.uiMode),v="expert"===b,{executePingForMachineAndWait:N}=it(),k=a.useRef(null),[C,w]=a.useState("machine"),[$,S]=a.useState([]),M=X(),I=q(),T=q(),[A,D]=a.useState(!1),[E,R]=a.useState(!1),[F,P]=a.useState(!1),[L,W]=a.useState(null),[ae,ie]=a.useState(!1);s.useEffect(()=>{"simple"===b&&"machine"!==C&&w("machine")},[b,C]);const{data:se=[],isLoading:ne,refetch:re}=r(n,p),{data:oe=[]}=o(n),ce=ft(k,{containerOffset:170,minRows:5,maxRows:50}),me=se,le=a.useCallback(e=>Xe(e,oe.map(e=>({repositoryGuid:e.repositoryGuid,repositoryName:e.repositoryName,grandGuid:e.grandGuid}))),[oe]),de=a.useCallback(e=>{u&&u(e)},[u]),ue=a.useCallback(e=>{x?x(e):(W(e),ie(!0))},[x]),fe=a.useCallback(()=>{ie(!1),W(null)},[]),{getFunctionsByCategory:je}=h(),be=a.useMemo(()=>je("machine").filter(e=>e&&!1!==e.showInMenu&&"mount"!==e.name&&"pull"!==e.name),[je]),ve=v&&U.isEnabled("assignToCluster"),Ne=a.useCallback(e=>{e.open&&e.machine?T.open(e.machine):T.close()},[T]),Ce=a.useCallback(e=>{e.open&&e.entityType&&e.entityIdentifier?M.open({entityType:e.entityType,entityIdentifier:e.entityIdentifier,entityName:e.entityName}):M.close()},[M]),Me=s.useMemo(()=>(({t:t,isExpertMode:a,uiMode:i,showActions:s,hasSplitView:n,canAssignToCluster:r,onEditMachine:o,onFunctionsMachine:c,handleDelete:m,handleRowClick:l,executePingForMachineAndWait:d,setAssignClusterModal:u,setAuditTraceModal:h,machineFunctions:p})=>{const g=[],x=we({title:t("machines:machineName"),dataIndex:"machineName",key:"machineName",maxLength:50,sorter:Ze("machineName"),renderWrapper:t=>e.jsxs(pe,{children:[e.jsx(Rt,{}),e.jsx("strong",{children:t})]})});return g.push($e({title:t("machines:status"),dataIndex:"vaultStatusTime",key:"status",statusMap:{online:{icon:e.jsx(V,{}),label:t("machines:connected"),color:"success"},offline:{icon:e.jsx(Ue,{}),label:t("machines:connectionFailed"),color:"error"},unknown:{icon:e.jsx(Ue,{}),label:t("machines:statusUnknown"),color:"default"}},sorter:Je(e=>{if(!e.vaultStatusTime)return 1/0;const t=new Date(e.vaultStatusTime+"Z");return((new Date).getTime()-t.getTime())/6e4<=3?0:1}),renderValue:(e,t)=>{if(!t.vaultStatusTime)return"unknown";const a=new Date(t.vaultStatusTime+"Z");return((new Date).getTime()-a.getTime())/6e4<=3?"online":"offline"}}),x),n||g.push(we({title:t("machines:team"),dataIndex:"teamName",key:"teamName",width:150,sorter:Ze("teamName"),renderWrapper:t=>e.jsx(Ot,{$variant:"team",children:t})})),n||(a?g.push(we({title:t("machines:region"),dataIndex:"regionName",key:"regionName",width:150,sorter:Ze("regionName"),renderText:e=>e||"-",renderWrapper:(t,a)=>"-"===a?e.jsx("span",{children:"-"}):e.jsx(Ot,{$variant:"region",children:t})}),we({title:t("machines:bridge"),dataIndex:"bridgeName",key:"bridgeName",width:150,sorter:Ze("bridgeName"),renderWrapper:t=>e.jsx(Ot,{$variant:"bridge",children:t})})):"simple"!==i&&g.push(we({title:t("bridges.bridge"),dataIndex:"bridgeName",key:"bridgeName",width:150,sorter:Ze("bridgeName"),renderWrapper:t=>e.jsx(Ot,{$variant:"bridge",children:t})}))),!n&&r&&g.push({title:t("machines:assignmentStatus.title"),key:"assignmentStatus",width:180,ellipsis:!0,render:(t,a)=>e.jsx(We,{machine:a})}),n||g.push({title:t("machines:queueItems"),dataIndex:"queueCount",key:"queueCount",width:100,align:"center",sorter:Ze("queueCount"),render:t=>e.jsx(Gt,{$isPositive:t>0,count:t,showZero:!0})}),s&&g.push(Se({title:t("common:table.actions"),width:O.DIMENSIONS.CARD_WIDTH,renderActions:a=>e.jsx(ke,{buttons:[{type:"view",icon:e.jsx(He,{}),tooltip:"common:viewDetails",onClick:()=>l(a),variant:"default",testIdSuffix:"view-details"},{type:"edit",icon:e.jsx(Ye,{}),tooltip:"common:actions.edit",onClick:()=>o?.(a)},{type:"remote",icon:e.jsx(et,{}),tooltip:"machines:remote",dropdownItems:[{key:"functions",label:t("machines:runAction"),icon:e.jsx(et,{}),children:[...p.filter(e=>!1!==e?.showInMenu).map(t=>({key:`function-${t?.name||"unknown"}`,label:e.jsx("span",{title:t?.description||"",children:t?.name||"Unknown"}),onClick:()=>c?.(a,t?.name)})),{type:"divider"},{key:"advanced",label:t("machines:advanced"),icon:e.jsx(et,{}),onClick:()=>c?.(a)}]},{key:"test",label:t("machines:connectivityTest"),icon:e.jsx(Ae,{}),onClick:async()=>{z("info",t("machines:testingConnection"));const e=await d(a,{priority:4,description:"Connectivity test",addedVia:"machine-table",timeout:15e3});e.success?z("success",t("machines:connectionSuccessful")):z("error",e.error||t("machines:connectionFailed"))}},...r?[{key:"assignCluster",label:a.cephClusterName?t("machines:changeClusterAssignment"):t("machines:assignToCluster"),icon:e.jsx(_,{}),onClick:()=>u({open:!0,machine:a})}]:[]]},{type:"trace",icon:e.jsx(B,{}),tooltip:"machines:trace",onClick:()=>h({open:!0,entityType:"Machine",entityIdentifier:a.machineName,entityName:a.machineName})},{type:"delete",icon:e.jsx(Q,{}),tooltip:"common:actions.delete",onClick:()=>m(a),danger:!0},{type:"custom",render:t=>e.jsx(Ke,{machine:t.machineName,teamName:t.teamName})}],record:a,idField:"machineName",testIdPrefix:"machine",t:t})})),g})({t:f,isExpertMode:v,uiMode:b,showActions:c,hasSplitView:Boolean(x),canAssignToCluster:ve,onEditMachine:l,onFunctionsMachine:d,handleDelete:de,handleRowClick:ue,executePingForMachineAndWait:N,setAssignClusterModal:Ne,setAuditTraceModal:Ce,machineFunctions:be}),[f,v,b,c,x,ve,l,d,de,ue,N,Ne,Ce,be]),Ie=ve?{selectedRowKeys:$,onChange:e=>{S(e)},getCheckboxProps:e=>({disabled:!1,"data-testid":`machine-checkbox-${e.machineName}`})}:void 0,Te=a.useMemo(()=>{const e={};return"machine"===C||me.forEach(t=>{let a="";if("bridge"===C)a=t.bridgeName;else if("team"===C)a=t.teamName;else if("region"===C)a=t.regionName||"Unknown";else{if("repository"===C){const a=le(t);if(0===a.length)return;return void a.forEach(a=>{const i=a.name;e[i]||(e[i]=[]),e[i].find(e=>e.machineName===t.machineName)||e[i].push(t)})}if("status"===C){const e=le(t);if(0===e.length)a="No Repositories";else{const t=e.some(e=>!e.accessible),i=e.some(e=>e.mounted&&e.docker_running),s=e.some(e=>e.mounted&&!e.docker_running),n=e.some(e=>!e.mounted);a=t?"Inaccessible":i?"Active (Running)":s?"Ready (Stopped)":n?"Not Mounted":"Unknown Status"}}else if("grand"===C){const a=le(t);if(0===a.length)return;return void a.forEach(a=>{let i="No Grand Repository";if(a.grandGuid){const e=oe.find(e=>e.repositoryGuid===a.grandGuid);e&&(i=e.repositoryName)}e[i]||(e[i]=[]),e[i].find(e=>e.machineName===t.machineName)||e[i].push(t)})}}a&&(e[a]||(e[a]=[]),e[a].push(t))}),e},[me,C,oe,le]);return e.jsxs(jt,{className:m,children:["simple"===b?null:e.jsx(kt,{children:e.jsxs(pe,{wrap:!0,size:"small",children:[e.jsx(he,{title:f("machines:machine"),children:e.jsx(Ct,{variant:"machine"===C?"primary":"default",icon:e.jsx(G,{}),onClick:()=>w("machine"),"data-testid":"machine-view-toggle-machine","aria-label":f("machines:machine")})}),e.jsx(wt,{}),e.jsx(he,{title:f("machines:groupByBridge"),children:e.jsx(Ct,{variant:"bridge"===C?"primary":"default",icon:e.jsx(_,{}),onClick:()=>w("bridge"),"data-testid":"machine-view-toggle-bridge","aria-label":f("machines:groupByBridge")})}),e.jsx(he,{title:f("machines:groupByTeam"),children:e.jsx(Ct,{variant:"team"===C?"primary":"default",icon:e.jsx(H,{}),onClick:()=>w("team"),"data-testid":"machine-view-toggle-team","aria-label":f("machines:groupByTeam")})}),v&&e.jsx(he,{title:f("machines:groupByRegion"),children:e.jsx(Ct,{variant:"region"===C?"primary":"default",icon:e.jsx(K,{}),onClick:()=>w("region"),"data-testid":"machine-view-toggle-region","aria-label":f("machines:groupByRegion")})}),e.jsx(he,{title:f("machines:groupByRepo"),children:e.jsx(Ct,{variant:"repository"===C?"primary":"default",icon:e.jsx(Z,{}),onClick:()=>w("repository"),"data-testid":"machine-view-toggle-repo","aria-label":f("machines:groupByRepo")})}),e.jsx(he,{title:f("machines:groupByStatus"),children:e.jsx(Ct,{variant:"status"===C?"primary":"default",icon:e.jsx(J,{}),onClick:()=>w("status"),"data-testid":"machine-view-toggle-status","aria-label":f("machines:groupByStatus")})}),e.jsx(he,{title:f("machines:groupByGrand"),children:e.jsx(Ct,{variant:"grand"===C?"primary":"default",icon:e.jsx(qe,{}),onClick:()=>w("grand"),"data-testid":"machine-view-toggle-grand","aria-label":f("machines:groupByGrand")})})]})}),ve&&0!==$.length?e.jsxs(vt,{children:[e.jsxs(pe,{size:"middle",children:[e.jsx(Nt,{children:f("machines:bulkActions.selected",{count:$.length})}),e.jsx(he,{title:f("common:actions.clearSelection"),children:e.jsx(xe,{size:"small",onClick:()=>S([]),"data-testid":"machine-bulk-clear-selection","aria-label":f("common:actions.clearSelection"),children:"Clear"})})]}),e.jsxs(pe,{size:"middle",children:[e.jsx(he,{title:f("machines:bulkActions.assignToCluster"),children:e.jsx(xe,{type:"primary",icon:e.jsx(_,{}),onClick:()=>D(!0),"data-testid":"machine-bulk-assign-cluster","aria-label":f("machines:bulkActions.assignToCluster")})}),e.jsx(he,{title:f("machines:bulkActions.removeFromCluster"),children:e.jsx(xe,{icon:e.jsx(_,{}),onClick:()=>R(!0),"data-testid":"machine-bulk-remove-cluster","aria-label":f("machines:bulkActions.removeFromCluster")})}),e.jsx(he,{title:f("machines:bulkActions.viewAssignmentStatus"),children:e.jsx(xe,{icon:e.jsx(Y,{}),onClick:()=>P(!0),"data-testid":"machine-bulk-view-status","aria-label":f("machines:bulkActions.viewAssignmentStatus")})})]})]}):null,"machine"===C?e.jsx(bt,{ref:k,children:e.jsx(ge,{columns:Me,dataSource:me,rowKey:"machineName",loading:ne,scroll:{x:"max-content"},rowSelection:Ie,rowClassName:e=>{const t="machine-table-row";return y?.machineName===e.machineName?`${t} machine-table-row--selected`:t},"data-testid":"machine-table",pagination:{pageSize:ce,showSizeChanger:!1,showTotal:(e,t)=>f("common:table.showingRecords",{start:t[0],end:t[1],total:e})},onRow:e=>({"data-testid":`machine-row-${e.machineName}`,onClick:t=>{const a=t.target;a.closest("button")||a.closest(".ant-dropdown")||a.closest(".ant-dropdown-menu")||j(`/machines/${e.machineName}/repositories`,{state:{machine:e}})}}),sticky:!0})}):(()=>{if(0===Object.keys(Te).length)return e.jsx(Wt,{children:e.jsx(ee,{variant:"minimal",image:ye.PRESENTED_IMAGE_SIMPLE,description:f("resources:repositories.noRepositories")})});const t={machine:"repository",bridge:"bridge",team:"team",region:"region",repository:"repository",status:"status",grand:"grand"},a={team:"var(--color-success)",bridge:"var(--color-primary)",region:"var(--color-info)",repository:"var(--color-secondary)",status:"var(--color-warning)",grand:"var(--color-secondary)"},i={bridge:e.jsx(_,{}),team:e.jsx(H,{}),region:e.jsx(K,{}),repository:e.jsx(Z,{}),status:e.jsx(J,{}),grand:e.jsx(qe,{})};return e.jsx($t,{children:Object.entries(Te).map(([s,n],r)=>{const o=t[C],c=a[o];return e.jsxs(St,{$isAlternate:r%2==0,children:[e.jsxs(Mt,{children:[e.jsx(It,{$color:c}),e.jsxs(pe,{size:"small",children:[e.jsxs(Tt,{children:["#",r+1]}),e.jsx(Lt,{$variant:o,icon:i[C],children:s}),e.jsxs(At,{children:[n.length," ",1===n.length?f("machines:machine"):f("machines:machines")]})]})]}),n.map((t,a)=>e.jsxs(Dt,{$isStriped:a%2!=0,onClick:()=>j(`/machines/${t.machineName}/repositories`,{state:{machine:t}}),"data-testid":`grouped-machine-row-${t.machineName}`,children:[e.jsxs(Et,{children:[e.jsx(Ft,{}),e.jsxs(Vt,{children:[e.jsx(Pt,{children:t.machineName}),e.jsxs(pe,{size:"small",children:[e.jsx(Ot,{$variant:"team",children:t.teamName}),t.bridgeName&&e.jsx(Ot,{$variant:"bridge",children:t.bridgeName}),t.regionName&&e.jsx(Ot,{$variant:"region",children:t.regionName})]})]})]}),e.jsx(he,{title:f("machines:viewRepos"),children:e.jsx(zt,{variant:"primary",icon:e.jsx(te,{}),onClick:e=>{e.stopPropagation(),j(`/machines/${t.machineName}/repositories`,{state:{machine:t}})},children:f("machines:viewRepos")})})]},t.machineName))]},s)})})})(),e.jsx(Pe,{open:M.isOpen,onCancel:M.close,entityType:M.entityType,entityIdentifier:M.entityIdentifier,entityName:M.entityName}),I.state.data&&e.jsx(Ee,{open:I.isOpen,onCancel:I.close,machineName:I.state.data.machineName,teamName:I.state.data.teamName,bridgeName:I.state.data.bridgeName,onQueueItemCreated:g}),T.state.data&&e.jsx(_e,{open:T.isOpen,machine:T.state.data,onCancel:T.close,onSuccess:()=>{T.close(),re()}}),e.jsx(_e,{open:A,machines:se.filter(e=>$.includes(e.machineName)),onCancel:()=>D(!1),onSuccess:()=>{D(!1),S([]),re()}}),e.jsx(Be,{open:E,machines:se.filter(e=>$.includes(e.machineName)),onCancel:()=>R(!1),onSuccess:()=>{R(!1),S([]),re()}}),e.jsx(Qe,{open:F,machines:se.filter(e=>$.includes(e.machineName)),onCancel:()=>P(!1)}),!x&&e.jsx(ze,{machine:L,visible:ae,onClose:fe})]})},Bt=f.div`
  display: flex;
  height: 100%;
  width: 100%;
  position: relative;
  overflow: hidden;
`,Qt=f.div`
  width: ${({$width:e})=>e};
  height: 100%;
  overflow: auto;
  min-width: ${({theme:e})=>e.dimensions.SPLIT_PANEL_MIN_WIDTH}px;
  transition: width 0.3s ease-in-out;
`,Xt=f.div`
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
`,qt=t=>{const{type:i,selectedResource:s,onResourceSelect:n,isPanelCollapsed:r=!0,onTogglePanelCollapse:o}=t,c=Oe(),[m,l]=a.useState(c),[d,u]=a.useState(!1),[h,p]=a.useState(!1);a.useEffect(()=>{l(c)},[c]),a.useEffect(()=>{if(!s){u(!1);const e=setTimeout(()=>{p(!1)},250);return()=>clearTimeout(e)}p(!0),requestAnimationFrame(()=>{u(!0)})},[s]);const g=e=>{n(e)},x=()=>{n(null)},y=r?Le.COLLAPSED_WIDTH:m;if("machine"===i){const a=s?`calc(100% - ${y}px)`:"100%";return e.jsxs(Bt,{"data-testid":"split-resource-view-container",children:[e.jsx(Qt,{$width:a,"data-testid":"split-resource-view-left-panel",children:e.jsx(_t,{...t,onRowClick:g,selectedMachine:s})}),h&&e.jsx(Xt,{$visible:d,$rightOffset:y,onClick:x,"data-testid":"split-resource-view-backdrop"}),s&&e.jsx(Ge,{type:"machineName"in s?"machine":"repositoryName"in s?"repository":"container",data:s,visible:!0,onClose:x,splitWidth:m,onSplitWidthChange:l,isCollapsed:r,onToggleCollapse:o,collapsedWidth:Le.COLLAPSED_WIDTH})]})}return null},Ut=f(ye)`
  && {
    padding: ${({theme:e})=>e.spacing.LG}px 0;
  }
`,Ht=f(je)`
  && {
    width: 100%;
  }
`,Kt=()=>{const{t:t}=Ve(["resources","machines","common"]),[s,h]=fe.useModal(),f=n(),j=i(),{teams:b,selectedTeams:v,setSelectedTeams:N,isLoading:k}=be(),{modalState:C,currentResource:w,openModal:$,closeModal:S}=ve("machine"),[M,I]=a.useState(null),[T,A]=a.useState(null),[D,E]=a.useState(null),[F,V]=a.useState(!0),[P,O]=a.useState({}),{state:L,open:G,close:W}=ae(),_=q(),{data:B=[],refetch:Q}=r(v.length>0?v:void 0,v.length>0),{data:X=[]}=o(v.length>0?v:void 0),{data:U=[]}=p(v.length>0?v:void 0),H=c(),K=m(),Z=l(),J=d(),Y=u(),{executeAction:ee,isExecuting:te}=Ce();a.useEffect(()=>{const e=f.state;e?.createRepository&&j("/credentials",{state:e,replace:!0})},[f,j]);const pe=e=>{I(e),e&&(A(null),E(null),V(!1))},ge=a.useCallback(e=>{tt({modal:s,t:t,resourceType:"machine",resourceName:e.machineName,translationNamespace:"machines",onConfirm:()=>J.mutateAsync({teamName:e.teamName,machineName:e.machineName}),onSuccess:()=>Q()})},[J,s,Q,t]),xe=a.useCallback(async e=>{try{if("create"===C.mode){const{autoSetup:a,...i}=e;if(await H.mutateAsync(i),z("success",t("machines:createSuccess")),a)try{await new Promise(e=>setTimeout(e,500));const a=await ee({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,functionName:"setup",params:{datastore_size:"95%",source:"apt-repo",rclone_source:"install-script",docker_source:"docker-repo",install_amd_driver:"auto",install_nvidia_driver:"auto"},priority:3,addedVia:"machine-creation-auto-setup",machineVault:e.vaultContent||"{}"});a.success&&(a.taskId?(z("info",t("machines:setupQueued")),G(a.taskId,e.machineName)):a.isQueued&&z("info",t("machines:setupQueuedForSubmission")))}catch{z("warning",t("machines:machineCreatedButSetupFailed"))}S(),Q()}else if(w){const t=w.machineName,a=e.machineName;a&&a!==t&&await K.mutateAsync({teamName:w.teamName,currentMachineName:t,newMachineName:a}),e.bridgeName&&e.bridgeName!==w.bridgeName&&await Z.mutateAsync({teamName:w.teamName,machineName:a||t,newBridgeName:e.bridgeName});const i=e.vaultContent;i&&i!==w.vaultContent&&await Y.mutateAsync({teamName:w.teamName,machineName:a||t,vaultContent:i,vaultVersion:w.vaultVersion+1}),S(),Q()}}catch{}},[S,H,w,ee,G,Q,t,C.mode,Z,K,Y]),ye=a.useCallback(async(e,t)=>{if(w)try{await Y.mutateAsync({teamName:w.teamName,machineName:w.machineName,vaultContent:e,vaultVersion:t}),S(),Q()}catch{}},[S,w,Q,Y]),je=a.useCallback(async e=>{if(w)try{const a=w.machineName,i=w.bridgeName,s=b.find(e=>e.teamName===w.teamName),n="string"==typeof e.params.repository?e.params.repository:void 0,r={teamName:w.teamName,machineName:a,bridgeName:i,functionName:e.function.name,params:e.params,priority:e.priority,addedVia:"machine-table",teamVault:s?.vaultContent||"{}",machineVault:w.vaultContent||"{}",vaultContent:"{}"};if(n){const e=X.find(e=>e.repositoryGuid===n);r.repositoryGuid=e?.repositoryGuid||n,r.vaultContent=e?.vaultContent||"{}"}if("pull"===e.function.name){const t="string"==typeof e.params.sourceType?e.params.sourceType:void 0,a="string"==typeof e.params.from?e.params.from:void 0;if("machine"===t&&a){const e=B.find(e=>e.machineName===a);e?.vaultContent&&(r.sourceMachineVault=e.vaultContent)}if("storage"===t&&a){const e=U.find(e=>e.storageName===a);e?.vaultContent&&(r.sourceStorageVault=e.vaultContent)}}const o=await ee(r);S(),o.success?o.taskId?(z("success",t("machines:queueItemCreated")),G(o.taskId,a)):o.isQueued&&z("info",t("resources:messages.highestPriorityQueued",{resourceType:"machine"})):z("error",o.error||t("resources:errors.failedToCreateQueueItem"))}catch{z("error",t("resources:errors.failedToCreateQueueItem"))}},[S,w,ee,B,G,X,U,t,b]),Ne=a.useCallback(async(e,a)=>{const i=g[a];if(!i)return void z("error",t("resources:errors.functionNotFound"));const s={};i.params&&Object.entries(i.params).forEach(([e,t])=>{t.default&&(s[e]=t.default)});const n=b.find(t=>t.teamName===e.teamName),r={teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,functionName:a,params:s,priority:4,addedVia:"machine-table-quick",teamVault:n?.vaultContent||"{}",machineVault:e.vaultContent||"{}",vaultContent:"{}"};try{const a=await ee(r);a.success?a.taskId?(z("success",t("machines:queueItemCreated")),G(a.taskId,e.machineName)):a.isQueued&&z("info",t("resources:messages.highestPriorityQueued",{resourceType:"machine"})):z("error",a.error||t("resources:errors.failedToCreateQueueItem")),O(t=>({...t,[e.machineName]:Date.now()}))}catch{z("error",t("resources:errors.failedToCreateQueueItem"))}},[ee,G,t,b]),ke=H.isPending||K.isPending||Z.isPending||te,we=Y.isPending,$e=C.data??w??void 0;return e.jsxs(e.Fragment,{children:[e.jsx(ie,{children:e.jsxs(se,{children:[e.jsx(ne,{level:3,children:t("machines:heading",{defaultValue:"Machines"})}),e.jsxs(re,{children:[e.jsx(se,{children:e.jsxs(oe,{children:[e.jsx(ce,{children:e.jsx(me,{children:e.jsx(Ht,{"data-testid":"machines-team-selector",teams:b,selectedTeams:v,onChange:N,loading:k,placeholder:t("teams.selectTeamToView")})})}),v.length>0&&e.jsxs(le,{children:[e.jsx(he,{title:t("machines:createMachine"),children:e.jsx(R,{iconOnly:!0,icon:e.jsx(de,{}),"data-testid":"machines-create-machine-button",onClick:()=>$("create"),"aria-label":t("machines:createMachine")})}),e.jsx(he,{title:t("machines:connectivityTest"),children:e.jsx(R,{iconOnly:!0,icon:e.jsx(Ae,{}),"data-testid":"machines-connectivity-test-button",onClick:()=>_.open(),disabled:0===B.length,"aria-label":t("machines:connectivityTest")})}),e.jsx(he,{title:t("common:actions.refresh"),children:e.jsx(R,{iconOnly:!0,icon:e.jsx(at,{}),"data-testid":"machines-refresh-button",onClick:()=>{Q(),O(e=>({...e,_global:Date.now()}))},"aria-label":t("common:actions.refresh")})})]})]})}),e.jsx(ue,{children:0===v.length?e.jsx(Ut,{image:Ut.PRESENTED_IMAGE_SIMPLE,description:t("teams.selectTeamPrompt")}):e.jsx(qt,{type:"machine",teamFilter:v,showFilters:!0,showActions:!0,onCreateMachine:()=>$("create"),onEditMachine:e=>$("edit",e),onVaultMachine:e=>$("vault",e),onFunctionsMachine:(e,t)=>{t?Ne(e,t):$("create",e)},onDeleteMachine:ge,enabled:v.length>0,refreshKeys:P,onQueueItemCreated:(e,t)=>{G(e,t)},selectedResource:M||T||D,onResourceSelect:e=>{e&&"machineName"in e?pe(e):e&&"repositoryName"in e?(pe(null),A(e),E(null),V(!1)):e&&"id"in e&&"state"in e?(pe(null),A(null),E(e),V(!1)):(pe(null),A(null),E(null))},isPanelCollapsed:F,onTogglePanelCollapse:()=>{V(e=>!e)}})})]})]})}),e.jsx(x,{"data-testid":"machines-machine-modal",open:C.open,onCancel:S,resourceType:"machine",mode:C.mode,existingData:$e,teamFilter:v.length>0?v:void 0,preselectedFunction:C.preselectedFunction,onSubmit:async e=>{const t=e;await xe(t)},onUpdateVault:"edit"===C.mode?ye:void 0,onFunctionSubmit:e=>je(e),isSubmitting:ke,isUpdatingVault:we,functionCategories:["machine","backup"],hiddenParams:[],defaultParams:{}}),e.jsx(y,{"data-testid":"machines-queue-trace-modal",taskId:L.taskId,open:L.open,onCancel:()=>{const e=L.machineName;W(),e&&O(t=>({...t,[e]:Date.now()})),Q()}}),e.jsx(yt,{"data-testid":"machines-connectivity-test-modal",open:_.isOpen,onClose:_.close,machines:B,teamFilter:v}),h]})};export{Kt as default};
