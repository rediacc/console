import{j as e,g as t}from"./chunk-BcoMUYMA.js";import{b as a,f as i,R as n,u as s}from"./chunk-Dx23Oqz1.js";import{u as r,a as o,b as c,c as m,d as l,e as d,f as u}from"./chunk-Czw9329s.js";import{u as h,a as p,F as g,U as x}from"./chunk-K0Guwoo4.js";import{Q as y}from"./chunk-fv5q0NeN.js";import{B as f,d as j,G as b,J as v,M as N,F as k,i as C,A as w,c as $,g as S,I as M,K as I,N as T,O as A,Q as D,U as R,V as E,e as F,l as V,p as P,m as O,X as L,Y as z,a as G,D as W,j as _,C as B,H as Q,Z as X,_ as q,$ as U,a0 as H,T as K,a1 as Z,y as J,a2 as Y,z as ee,a3 as te,a4 as ae,a5 as ie,a6 as ne,a7 as se,a8 as re,a9 as oe,aa as ce,ab as me,ac as le,ad as de,ae as ue,af as he}from"../index-ClLYmVcU.js";import{x as pe,E as ge,M as xe}from"./chunk-3AIKJ4WW.js";import{T as ye,u as fe}from"./chunk-aBew7EzQ.js";import{u as je}from"./chunk-C6iGxybb.js";import{u as be,A as ve,a as Ne}from"./chunk-bwjbtFnR.js";import{c as ke,a as Ce,b as we}from"./chunk-YyURSuLu.js";import"./chunk-D2gwLR4U.js";import{R as $e}from"./chunk-Ca8Srxg0.js";import{u as Se}from"./chunk-CGM-kEDt.js";import{u as Me,W as Ie}from"./chunk-kwA1PAUU.js";import{w as Te,R as Ae}from"./chunk-2pQRDED0.js";import{C as De}from"./chunk-BaOYACiF.js";import{S as Re}from"./chunk-snNitAwj.js";import{u as Ee}from"./chunk-DsYhoPUY.js";import{A as Fe}from"./chunk-DVHl7BYm.js";import{M as Ve,u as Pe,D as Oe,U as Le}from"./chunk-BqLpC4ZP.js";import{M as ze,A as Ge,R as We,V as _e}from"./chunk-BI1GZumX.js";import{g as Be}from"./chunk-GqWjj4O2.js";import{B as Qe}from"./chunk-C1gTcGfb.js";import{D as Xe,E as qe,L as Ue}from"./chunk-DkPRidqQ.js";import{c as He,a as Ke}from"./chunk-BKxNWyZX.js";import{E as Ze}from"./chunk-eNJA9ReT.js";import{F as Je}from"./chunk-B5mJO5cq.js";import{c as Ye}from"./chunk-CfGA4Om9.js";import{R as et}from"./chunk-KA-m8Hjj.js";import"./chunk-CWN1N_SP.js";import"./chunk-DB6ez0TU.js";import"./chunk-CSYUxvNf.js";import"./chunk-DsYZc31D.js";import"./chunk-DDaRaurs.js";import"./chunk-ClpoY1yM.js";import"./chunk-CxyJqyR6.js";import"./chunk-BBMsrcM9.js";import"./chunk-D6fzeF6b.js";import"./chunk-DitrKKxw.js";import"./chunk-BnN21jfu.js";import"./chunk-D6iH8jj2.js";import"./chunk-CSHWoLep.js";import"./chunk-BYtbR3Vn.js";import"./chunk-CrAvvfvb.js";import"./chunk-QKwhNBU8.js";import"./chunk-BC1-c3vx.js";import"./chunk-DhpoEw86.js";import"./chunk-wetoU9f5.js";import"./chunk-DbJjGBdA.js";import"./chunk-yhVPGZX_.js";import"./forkTokenService.ts-BaKZ4lK-.js";import"./chunk-DS5kI2q4.js";function tt(e){const{buildQueueVault:t}=Me();be();const i=Se(),{data:n}=f(),s=a.useCallback(async e=>{try{const a=function(e,t){if(e.teamVault&&"{}"!==e.teamVault)return e.teamVault;const a=t?.find(t=>t.teamName===e.teamName);return a?.vaultContent||"{}"}(e,n),s=await async function(e,t,a){const i=4,n="ping-service",s="{}";return a({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,functionName:"ping",params:{},priority:e.priority||i,addedVia:e.addedVia||n,machineVault:e.machineVault||s,teamVault:t,repositoryVault:e.vaultContent||s})}(e,a,t),r=await async function(e,t,a){const i=4,n=await a.mutateAsync({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,queueVault:t,priority:e.priority||i});return s=n,(e=>{if("object"!=typeof e||null===e)return!1;const t=e,a=void 0===t.taskId||"string"==typeof t.taskId,i=void 0===t.isQueued||"boolean"==typeof t.isQueued;return a&&i})(s)?s:{};var s}(e,s,i);return{taskId:r?.taskId,success:!!r?.taskId||!!r?.isQueued}}catch(a){return{success:!1,error:a instanceof Error?a.message:"Failed to execute ping function"}}},[t,i,n]),r=a.useCallback(async(e,t)=>s({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,priority:t?.priority,description:t?.description,addedVia:t?.addedVia,machineVault:e.vaultContent||"{}"}),[s]),o=a.useCallback(async(e,t)=>{const a=await s(e);if(!a.success||!a.taskId)return a;const i=await Te(a.taskId,t);return{...a,completionResult:i,success:i.success,error:i.success?void 0:i.message}},[s]),c=a.useCallback(async(e,t)=>o({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,priority:t?.priority,description:t?.description,addedVia:t?.addedVia,machineVault:e.vaultContent||"{}"},t?.timeout),[o]);return{executePing:s,executePingForMachine:r,executePingAndWait:o,executePingForMachineAndWait:c,waitForQueueItemCompletion:Te,isLoading:i.isPending}}const at=b`
  0% {
    opacity: 0.65;
  }
  50% {
    opacity: 1;
  }
  100% {
    opacity: 0.65;
  }
`,it=j(v)`
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
`,nt=j(N)`
  width: 100%;
`,st=j(k).attrs({$gap:"XS"})``,rt=j(C)`
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
`,ot=j.div`
  padding: ${({theme:e})=>e.spacing.MD}px;
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
  background-color: ${({theme:e})=>e.colors.bgSecondary};
`,ct=j(w)`
  gap: ${({theme:e})=>e.spacing.XL}px;
`,mt=j(k).attrs({$gap:"XS"})``,lt=j($).attrs({weight:"semibold"})`
  && {
    color: ${({theme:e,$variant:t})=>"success"===t?e.colors.success:"error"===t?e.colors.error:e.colors.textPrimary};
  }
`,dt=j.div`
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
`,ut=j(S).attrs({variant:"neutral"})`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.MD}px;
  }
`;j(S)`
  && {
    text-transform: capitalize;
  }
`;const ht=j($)`
  && {
    color: ${({theme:e,$isError:t})=>t?e.colors.error:e.colors.textPrimary};
  }
`,pt=j.div`
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
  font-size: ${({theme:e})=>e.fontSize.SM}px;
`,gt=({open:t,onClose:i,machines:n})=>{const{t:s}=Ee(["machines","common"]),[r,o]=a.useState([]),[c,m]=a.useState(!1),[l,d]=a.useState(0),[u,h]=a.useState(-1),{executePingForMachine:p,waitForQueueItemCompletion:g}=tt();a.useEffect(()=>{if(t&&n.length>0){const e=n.map(e=>({machineName:e.machineName,teamName:e.teamName,bridgeName:e.bridgeName,status:"pending"}));o(e),d(0),h(-1)}},[t,n]);const x=e=>e.success?s("machines:connectionSuccessful"):"TIMEOUT"===e.status?s("machines:testTimeout"):e.message||s("machines:connectionFailed"),y=async(e,t)=>{const a=Date.now();o(e=>e.map((e,a)=>a===t?{...e,status:"testing",timestamp:(new Date).toISOString()}:e));try{const i=await p(e,{priority:4,description:"Connectivity test",addedVia:"connectivity-test"});if(!i.success||!i.taskId)throw new Error(i.error||"Failed to create test task");{o(e=>e.map((e,a)=>a===t?{...e,taskId:i.taskId}:e));const e=await g(i.taskId),n=Date.now()-a;o(a=>a.map((a,i)=>i===t?{...a,status:e.success?"success":"failed",message:x(e),duration:n}:a))}}catch(i){const e=i instanceof Error?i.message:"Failed to create test task",n=Date.now()-a;o(a=>a.map((a,i)=>i===t?{...a,status:"failed",message:e,duration:n}:a))}},f=ke({title:s("machines:team"),dataIndex:"teamName",key:"teamName",renderWrapper:t=>e.jsx(ut,{children:t})}),j=ke({title:s("machines:bridge"),dataIndex:"bridgeName",key:"bridgeName",renderWrapper:t=>e.jsx(ut,{children:t})}),b=Ce({title:s("machines:status"),dataIndex:"status",key:"status",width:140,statusMap:{pending:{color:"default",label:s("machines:pending"),icon:e.jsx(O,{})},testing:{color:"blue",label:s("machines:testing"),icon:e.jsx(Re,{spin:!0})},success:{color:"success",label:s("machines:connected"),icon:e.jsx(P,{})},failed:{color:"error",label:s("machines:failed"),icon:e.jsx(De,{})}}}),v=ke({title:s("machines:message"),dataIndex:"message",key:"message",ellipsis:!0,renderText:e=>e||"-"}),N=[{title:s("machines:machineName"),dataIndex:"machineName",key:"machineName",render:(t,a)=>e.jsxs(M,{"data-testid":`connectivity-machine-${t}`,children:[e.jsx(I,{$variant:a.status,children:(()=>{switch(a.status){case"testing":return e.jsx(Re,{spin:!0,"data-testid":`connectivity-status-icon-testing-${t}`});case"success":return e.jsx(P,{"data-testid":`connectivity-status-icon-success-${t}`});case"failed":return e.jsx(De,{"data-testid":`connectivity-status-icon-failed-${t}`});default:return e.jsx(O,{"data-testid":`connectivity-status-icon-pending-${t}`})}})()}),e.jsx($,{weight:"semibold",children:t})]})},f,j,{...b,render:(t,a,i)=>e.jsx("span",{"data-testid":`connectivity-status-tag-${a.machineName}-${t}`,children:b.render?.(t,a,i)})},{title:s("machines:responseTime"),dataIndex:"duration",key:"duration",width:120,render:e=>e?e<1e3?`${e}ms`:`${(e/1e3).toFixed(1)}s`:"-"},{...v,render:(t,a,i)=>{if(!t)return v.render?.(t,a,i);const n=v.render?.(t,a,i);return e.jsx(ht,{$isError:"failed"===a.status,children:n})}}];return e.jsx(it,{"data-testid":"connectivity-modal",title:e.jsxs(V,{direction:"horizontal",gap:"sm",align:"center",children:[e.jsx(Ie,{}),e.jsx("span",{children:s("machines:connectivityTest")})]}),open:t,onCancel:i,className:T.Large,destroyOnClose:!0,footer:e.jsxs(R,{children:[e.jsx(E,{icon:e.jsx(Re,{}),onClick:async()=>{m(!0);for(let a=0;a<n.length;a++)h(a),d(Math.round(a/n.length*100)),await y(n[a],a);d(100),m(!1),h(-1);const e=r.filter(e=>"success"===e.status).length,t=r.filter(e=>"failed"===e.status).length;0===t?L("success",s("machines:allMachinesConnected",{count:e})):L("warning",s("machines:machinesConnectedWithFailures",{successCount:e,failedCount:t}))},disabled:c||0===n.length,loading:c,"data-testid":"connectivity-run-test-button",children:s(c?"machines:testing":"machines:runTest")}),e.jsx(F,{title:"Close",children:e.jsx(E,{iconOnly:!0,icon:e.jsx(De,{}),onClick:i,"data-testid":"connectivity-close-button","aria-label":"Close"})})]}),children:e.jsx(nt,{children:e.jsxs(A,{children:[c&&e.jsxs(st,{"data-testid":"connectivity-progress-container",children:[e.jsx(rt,{percent:l,status:"active","data-testid":"connectivity-progress-bar"}),u>=0&&u<n.length&&e.jsx($,{size:"xs",color:"secondary","data-testid":"connectivity-progress-text",children:s("machines:testingMachine",{machineName:n[u].machineName})})]}),e.jsx(pt,{children:e.jsx(D,{message:s("machines:connectivityTestDescription"),variant:"info",showIcon:!0,icon:e.jsx(Ie,{}),"data-testid":"connectivity-info-alert"})}),e.jsx(dt,{children:e.jsx($e,{columns:N,dataSource:r,rowKey:"machineName",pagination:!1,scroll:{y:400},loading:0===n.length,rowClassName:e=>`status-${e.status}`,"data-testid":"connectivity-results-table"})}),!c&&r.some(e=>"pending"!==e.status)&&e.jsx(ot,{"data-testid":"connectivity-summary-statistics",children:e.jsxs(ct,{children:[e.jsxs(mt,{"data-testid":"connectivity-total-machines",children:[e.jsxs($,{color:"secondary",children:[s("machines:totalMachines"),":"]}),e.jsx(lt,{children:n.length})]}),e.jsxs(mt,{"data-testid":"connectivity-connected-count",children:[e.jsxs($,{color:"secondary",children:[s("machines:connected"),":"]}),e.jsx(lt,{$variant:"success",children:r.filter(e=>"success"===e.status).length})]}),e.jsxs(mt,{"data-testid":"connectivity-failed-count",children:[e.jsxs($,{color:"secondary",children:[s("machines:failed"),":"]}),e.jsx(lt,{$variant:"error",children:r.filter(e=>"failed"===e.status).length})]}),e.jsxs(mt,{"data-testid":"connectivity-average-response",children:[e.jsxs($,{color:"secondary",children:[s("machines:averageResponse"),":"]}),e.jsx(lt,{children:(()=>{const e=r.filter(e=>"success"===e.status&&e.duration);if(0===e.length)return"-";const t=e.reduce((e,t)=>e+(t.duration||0),0)/e.length;return t<1e3?`${Math.round(t)}ms`:`${(t/1e3).toFixed(1)}s`})()})]})]})})]})})})},xt=(e,t={})=>{const{rowHeight:i=54,headerHeight:n=55,paginationHeight:s=64,containerOffset:r=32,minRows:o=5,maxRows:c=100}=t,[m,l]=a.useState(10),d=a.useRef(null),u=a.useCallback(()=>{if(!e.current)return;const t=e.current.offsetHeight-n-s-r,a=Math.floor(t/i),m=Math.max(o,Math.min(c,a));l(m)},[e,i,n,s,r,o,c]),h=a.useRef(null);return a.useEffect(()=>(h.current=((e,t=300)=>{let a=null;const i=()=>{a&&clearTimeout(a),a=setTimeout(()=>{e()},t)};return i.cancel=()=>{a&&(clearTimeout(a),a=null)},i})(u,300),()=>{h.current?.cancel()}),[u]),a.useEffect(()=>(u(),e.current&&window.ResizeObserver&&(d.current=new ResizeObserver(()=>{h.current?.()}),d.current.observe(e.current)),()=>{d.current&&d.current.disconnect(),h.current?.cancel()}),[u,e]),m},yt=j(k).attrs({$gap:"MD"})`
  height: 100%;

  /* Custom selection state - RediaccTable handles hover via interactive prop */
  .machine-table-row--selected td {
    background-color: var(--color-bg-selected);
  }
`,ft=j.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
`,jt=j.div`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
  padding: ${({theme:e})=>e.spacing.SM}px ${({theme:e})=>e.spacing.MD}px;
  background-color: var(--color-bg-secondary);
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border: 1px solid var(--color-border-secondary);
  gap: ${({theme:e})=>e.spacing.MD}px;
`,bt=j.span`
  font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
  color: var(--color-text-primary);
`,vt=j.div`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
`,Nt=j(E)`
  && {
    min-width: 42px;
  }
`,kt=j.span`
  width: 1px;
  height: ${({theme:e})=>e.spacing.LG}px;
  background-color: var(--color-border-secondary);
  margin: 0 ${({theme:e})=>e.spacing.SM}px;
`,Ct=j.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XL}px;
`,wt=j(G)`
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
`,$t=j(M)`
  padding: ${({theme:e})=>e.spacing.XS}px 0;
`,St=j.div`
  width: ${({theme:e})=>e.spacing.XS}px;
  height: ${z.DIMENSIONS.ICON_XL}px;
  border-radius: ${({theme:e})=>e.borderRadius.SM}px;
  background-color: ${({$color:e})=>e||"var(--color-text-secondary)"};
`,Mt=j.span`
  font-size: ${({theme:e})=>e.fontSize.LG}px;
  font-weight: ${({theme:e})=>e.fontWeight.BOLD};
  color: var(--color-text-primary);
`,It=j.span`
  font-size: ${({theme:e})=>e.fontSize.SM}px;
  color: var(--color-text-secondary);
`,Tt=j.div`
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
`,At=j.div`
  display: flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.LG}px;
`,Dt=j(W)`
  font-size: ${z.DIMENSIONS.ICON_MD}px;
  color: var(--color-primary);
`,Rt=j(Dt)`
  font-size: ${z.DIMENSIONS.ICON_LG}px;
`,Et=j.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XS}px;
`,Ft=j.span`
  font-size: ${({theme:e})=>e.fontSize.MD}px;
  font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
  color: var(--color-text-primary);
`,Vt=j(E)`
  && {
    /* Maintain compact pill styling to mirror historical control surface */
    gap: ${({theme:e})=>e.spacing.XS}px;
  }
`,Pt=j(S).attrs(({$preset:e,$variant:t})=>({preset:e||t,borderless:!0}))``,Ot=j(S).attrs(({$preset:e,$variant:t})=>({preset:e||t,borderless:!0,size:"md"}))`
  && {
    font-size: ${({theme:e})=>e.fontSize.MD}px;
    padding: ${({theme:e})=>e.spacing.XS}px ${({theme:e})=>e.spacing.MD}px;
  }
`,Lt=j(_)`
  && .ant-badge-count {
    background-color: ${({$isPositive:e})=>e?"var(--color-success)":"var(--color-border-secondary)"};
    color: ${({$isPositive:e})=>e?"var(--color-text-inverse)":"var(--color-text-secondary)"};
  }
`,zt=j.div`
  margin-top: ${({theme:e})=>2*e.spacing.XXL}px;
`,Gt=({teamFilter:s,showActions:c=!0,className:m="",onEditMachine:l,onFunctionsMachine:d,onDeleteMachine:u,enabled:p=!0,onQueueItemCreated:g,onRowClick:x,selectedMachine:y})=>{const{t:f}=Ee(["machines","common","functions","resources"]),j=i(),b=t(e=>e.ui.uiMode),v="expert"===b,{executePingForMachineAndWait:N}=tt(),k=a.useRef(null),[C,w]=a.useState("machine"),[$,S]=a.useState([]),M=q(),I=U(),T=U(),[A,D]=a.useState(!1),[R,V]=a.useState(!1),[O,G]=a.useState(!1),[_,ie]=a.useState(null),[ne,se]=a.useState(!1);n.useEffect(()=>{"simple"===b&&"machine"!==C&&w("machine")},[b,C]);const{data:re=[],isLoading:oe,refetch:ce}=r(s,p),{data:me=[]}=o(s),le=xt(k,{containerOffset:170,minRows:5,maxRows:50}),de=re,ue=a.useCallback(e=>Be(e,me.map(e=>({repositoryGuid:e.repositoryGuid,repositoryName:e.repositoryName,grandGuid:e.grandGuid}))),[me]),he=a.useCallback(e=>{u&&u(e)},[u]),xe=a.useCallback(e=>{x?x(e):(ie(e),se(!0))},[x]),ye=a.useCallback(()=>{se(!1),ie(null)},[]),{getFunctionsByCategory:fe}=h(),je=a.useMemo(()=>fe("machine").filter(e=>e&&!1!==e.showInMenu&&"mount"!==e.name&&"pull"!==e.name),[fe]),be=v&&H.isEnabled("assignToCluster"),Ne=a.useCallback(e=>{e.open&&e.machine?T.open(e.machine):T.close()},[T]),Se=a.useCallback(e=>{e.open&&e.entityType&&e.entityIdentifier?M.open({entityType:e.entityType,entityIdentifier:e.entityIdentifier,entityName:e.entityName}):M.close()},[M]),Me=n.useMemo(()=>(({t:t,isExpertMode:a,uiMode:i,showActions:n,hasSplitView:s,canAssignToCluster:r,onEditMachine:o,onFunctionsMachine:c,handleDelete:m,handleRowClick:l,executePingForMachineAndWait:d,setAssignClusterModal:u,setAuditTraceModal:h,machineFunctions:p})=>{const g=[],x=ke({title:t("machines:machineName"),dataIndex:"machineName",key:"machineName",maxLength:50,sorter:He("machineName"),renderWrapper:t=>e.jsxs(pe,{children:[e.jsx(Dt,{}),e.jsx("strong",{children:t})]})});return g.push(Ce({title:t("machines:status"),dataIndex:"vaultStatusTime",key:"status",statusMap:{online:{icon:e.jsx(P,{}),label:t("machines:connected"),color:"success"},offline:{icon:e.jsx(Xe,{}),label:t("machines:connectionFailed"),color:"error"},unknown:{icon:e.jsx(Xe,{}),label:t("machines:statusUnknown"),color:"default"}},sorter:Ke(e=>{if(!e.vaultStatusTime)return 1/0;const t=new Date(e.vaultStatusTime+"Z");return((new Date).getTime()-t.getTime())/6e4<=3?0:1}),renderValue:(e,t)=>{if(!t.vaultStatusTime)return"unknown";const a=new Date(t.vaultStatusTime+"Z");return((new Date).getTime()-a.getTime())/6e4<=3?"online":"offline"}}),x),s||g.push(ke({title:t("machines:team"),dataIndex:"teamName",key:"teamName",width:150,sorter:He("teamName"),renderWrapper:t=>e.jsx(Pt,{$variant:"team",children:t})})),s||(a?g.push(ke({title:t("machines:region"),dataIndex:"regionName",key:"regionName",width:150,sorter:He("regionName"),renderText:e=>e||"-",renderWrapper:(t,a)=>"-"===a?e.jsx("span",{children:"-"}):e.jsx(Pt,{$variant:"region",children:t})}),ke({title:t("machines:bridge"),dataIndex:"bridgeName",key:"bridgeName",width:150,sorter:He("bridgeName"),renderWrapper:t=>e.jsx(Pt,{$variant:"bridge",children:t})})):"simple"!==i&&g.push(ke({title:t("bridges.bridge"),dataIndex:"bridgeName",key:"bridgeName",width:150,sorter:He("bridgeName"),renderWrapper:t=>e.jsx(Pt,{$variant:"bridge",children:t})}))),!s&&r&&g.push({title:t("machines:assignmentStatus.title"),key:"assignmentStatus",width:180,ellipsis:!0,render:(t,a)=>e.jsx(ze,{machine:a})}),s||g.push({title:t("machines:queueItems"),dataIndex:"queueCount",key:"queueCount",width:100,align:"center",sorter:He("queueCount"),render:t=>e.jsx(Lt,{$isPositive:t>0,count:t,showZero:!0})}),n&&g.push(we({title:t("common:table.actions"),width:z.DIMENSIONS.CARD_WIDTH,renderActions:a=>e.jsx(ve,{buttons:[{type:"view",icon:e.jsx(qe,{}),tooltip:"common:viewDetails",onClick:()=>l(a),variant:"default",testIdSuffix:"view-details"},{type:"edit",icon:e.jsx(Ze,{}),tooltip:"common:actions.edit",onClick:()=>o?.(a)},{type:"remote",icon:e.jsx(Je,{}),tooltip:"machines:remote",dropdownItems:[{key:"functions",label:t("machines:runAction"),icon:e.jsx(Je,{}),children:[...p.filter(e=>!1!==e?.showInMenu).map(t=>({key:`function-${t?.name||"unknown"}`,label:e.jsx("span",{title:t?.description||"",children:t?.name||"Unknown"}),onClick:()=>c?.(a,t?.name)})),{type:"divider"},{key:"advanced",label:t("machines:advanced"),icon:e.jsx(Je,{}),onClick:()=>c?.(a)}]},{key:"test",label:t("machines:connectivityTest"),icon:e.jsx(Ie,{}),onClick:async()=>{L("info",t("machines:testingConnection"));const e=await d(a,{priority:4,description:"Connectivity test",addedVia:"machine-table",timeout:15e3});e.success?L("success",t("machines:connectionSuccessful")):L("error",e.error||t("machines:connectionFailed"))}},...r?[{key:"assignCluster",label:a.cephClusterName?t("machines:changeClusterAssignment"):t("machines:assignToCluster"),icon:e.jsx(B,{}),onClick:()=>u({open:!0,machine:a})}]:[]]},{type:"trace",icon:e.jsx(Q,{}),tooltip:"machines:trace",onClick:()=>h({open:!0,entityType:"Machine",entityIdentifier:a.machineName,entityName:a.machineName})},{type:"delete",icon:e.jsx(X,{}),tooltip:"common:actions.delete",onClick:()=>m(a),danger:!0},{type:"custom",render:t=>e.jsx(Ue,{machine:t.machineName,teamName:t.teamName})}],record:a,idField:"machineName",testIdPrefix:"machine",t:t})})),g})({t:f,isExpertMode:v,uiMode:b,showActions:c,hasSplitView:Boolean(x),canAssignToCluster:be,onEditMachine:l,onFunctionsMachine:d,handleDelete:he,handleRowClick:xe,executePingForMachineAndWait:N,setAssignClusterModal:Ne,setAuditTraceModal:Se,machineFunctions:je}),[f,v,b,c,x,be,l,d,he,xe,N,Ne,Se,je]),Te=be?{selectedRowKeys:$,onChange:e=>{S(e)},getCheckboxProps:e=>({disabled:!1,"data-testid":`machine-checkbox-${e.machineName}`})}:void 0,De=a.useMemo(()=>{const e={};return"machine"===C||de.forEach(t=>{let a="";if("bridge"===C)a=t.bridgeName;else if("team"===C)a=t.teamName;else if("region"===C)a=t.regionName||"Unknown";else{if("repository"===C){const a=ue(t);if(0===a.length)return;return void a.forEach(a=>{const i=a.name;e[i]||(e[i]=[]),e[i].find(e=>e.machineName===t.machineName)||e[i].push(t)})}if("status"===C){const e=ue(t);if(0===e.length)a="No Repositories";else{const t=e.some(e=>!e.accessible),i=e.some(e=>e.mounted&&e.docker_running),n=e.some(e=>e.mounted&&!e.docker_running),s=e.some(e=>!e.mounted);a=t?"Inaccessible":i?"Active (Running)":n?"Ready (Stopped)":s?"Not Mounted":"Unknown Status"}}else if("grand"===C){const a=ue(t);if(0===a.length)return;return void a.forEach(a=>{let i="No Grand Repository";if(a.grandGuid){const e=me.find(e=>e.repositoryGuid===a.grandGuid);e&&(i=e.repositoryName)}e[i]||(e[i]=[]),e[i].find(e=>e.machineName===t.machineName)||e[i].push(t)})}}a&&(e[a]||(e[a]=[]),e[a].push(t))}),e},[de,C,me,ue]);return e.jsxs(yt,{className:m,children:["simple"===b?null:e.jsx(vt,{children:e.jsxs(pe,{wrap:!0,size:"small",children:[e.jsx(F,{title:f("machines:machine"),children:e.jsx(Nt,{variant:"machine"===C?"primary":"default",icon:e.jsx(W,{}),onClick:()=>w("machine"),"data-testid":"machine-view-toggle-machine","aria-label":f("machines:machine")})}),e.jsx(kt,{}),e.jsx(F,{title:f("machines:groupByBridge"),children:e.jsx(Nt,{variant:"bridge"===C?"primary":"default",icon:e.jsx(B,{}),onClick:()=>w("bridge"),"data-testid":"machine-view-toggle-bridge","aria-label":f("machines:groupByBridge")})}),e.jsx(F,{title:f("machines:groupByTeam"),children:e.jsx(Nt,{variant:"team"===C?"primary":"default",icon:e.jsx(K,{}),onClick:()=>w("team"),"data-testid":"machine-view-toggle-team","aria-label":f("machines:groupByTeam")})}),v&&e.jsx(F,{title:f("machines:groupByRegion"),children:e.jsx(Nt,{variant:"region"===C?"primary":"default",icon:e.jsx(Z,{}),onClick:()=>w("region"),"data-testid":"machine-view-toggle-region","aria-label":f("machines:groupByRegion")})}),e.jsx(F,{title:f("machines:groupByRepo"),children:e.jsx(Nt,{variant:"repository"===C?"primary":"default",icon:e.jsx(J,{}),onClick:()=>w("repository"),"data-testid":"machine-view-toggle-repo","aria-label":f("machines:groupByRepo")})}),e.jsx(F,{title:f("machines:groupByStatus"),children:e.jsx(Nt,{variant:"status"===C?"primary":"default",icon:e.jsx(Y,{}),onClick:()=>w("status"),"data-testid":"machine-view-toggle-status","aria-label":f("machines:groupByStatus")})}),e.jsx(F,{title:f("machines:groupByGrand"),children:e.jsx(Nt,{variant:"grand"===C?"primary":"default",icon:e.jsx(Qe,{}),onClick:()=>w("grand"),"data-testid":"machine-view-toggle-grand","aria-label":f("machines:groupByGrand")})})]})}),be&&0!==$.length?e.jsxs(jt,{children:[e.jsxs(pe,{size:"middle",children:[e.jsx(bt,{children:f("machines:bulkActions.selected",{count:$.length})}),e.jsx(F,{title:f("common:actions.clearSelection"),children:e.jsx(E,{onClick:()=>S([]),"data-testid":"machine-bulk-clear-selection","aria-label":f("common:actions.clearSelection"),children:"Clear"})})]}),e.jsxs(pe,{size:"middle",children:[e.jsx(F,{title:f("machines:bulkActions.assignToCluster"),children:e.jsx(E,{variant:"primary",icon:e.jsx(B,{}),onClick:()=>D(!0),"data-testid":"machine-bulk-assign-cluster","aria-label":f("machines:bulkActions.assignToCluster")})}),e.jsx(F,{title:f("machines:bulkActions.removeFromCluster"),children:e.jsx(E,{icon:e.jsx(B,{}),onClick:()=>V(!0),"data-testid":"machine-bulk-remove-cluster","aria-label":f("machines:bulkActions.removeFromCluster")})}),e.jsx(F,{title:f("machines:bulkActions.viewAssignmentStatus"),children:e.jsx(E,{icon:e.jsx(ee,{}),onClick:()=>G(!0),"data-testid":"machine-bulk-view-status","aria-label":f("machines:bulkActions.viewAssignmentStatus")})})]})]}):null,"machine"===C?e.jsx(ft,{ref:k,children:e.jsx($e,{columns:Me,dataSource:de,rowKey:"machineName",loading:oe,interactive:!0,selectable:!0,scroll:{x:"max-content"},rowSelection:Te,rowClassName:e=>{const t="machine-table-row";return y?.machineName===e.machineName?`${t} machine-table-row--selected`:t},"data-testid":"machine-table",pagination:{pageSize:le,showSizeChanger:!1,showTotal:(e,t)=>f("common:table.showingRecords",{start:t[0],end:t[1],total:e})},onRow:e=>({"data-testid":`machine-row-${e.machineName}`,onClick:t=>{const a=t.target;a.closest("button")||a.closest(".ant-dropdown")||a.closest(".ant-dropdown-menu")||j(`/machines/${e.machineName}/repositories`,{state:{machine:e}})}}),sticky:!0})}):(()=>{if(0===Object.keys(De).length)return e.jsx(zt,{children:e.jsx(te,{variant:"minimal",image:ge.PRESENTED_IMAGE_SIMPLE,description:f("resources:repositories.noRepositories")})});const t={machine:"repository",bridge:"bridge",team:"team",region:"region",repository:"repository",status:"status",grand:"grand"},a={team:"var(--color-success)",bridge:"var(--color-primary)",region:"var(--color-info)",repository:"var(--color-secondary)",status:"var(--color-warning)",grand:"var(--color-secondary)"},i={bridge:e.jsx(B,{}),team:e.jsx(K,{}),region:e.jsx(Z,{}),repository:e.jsx(J,{}),status:e.jsx(Y,{}),grand:e.jsx(Qe,{})};return e.jsx(Ct,{children:Object.entries(De).map(([n,s],r)=>{const o=t[C],c=a[o];return e.jsxs(wt,{$isAlternate:r%2==0,children:[e.jsxs($t,{children:[e.jsx(St,{$color:c}),e.jsxs(pe,{size:"small",children:[e.jsxs(Mt,{children:["#",r+1]}),e.jsx(Ot,{$variant:o,icon:i[C],children:n}),e.jsxs(It,{children:[s.length," ",1===s.length?f("machines:machine"):f("machines:machines")]})]})]}),s.map((t,a)=>e.jsxs(Tt,{$isStriped:a%2!=0,onClick:()=>j(`/machines/${t.machineName}/repositories`,{state:{machine:t}}),"data-testid":`grouped-machine-row-${t.machineName}`,children:[e.jsxs(At,{children:[e.jsx(Rt,{}),e.jsxs(Et,{children:[e.jsx(Ft,{children:t.machineName}),e.jsxs(pe,{size:"small",children:[e.jsx(Pt,{$variant:"team",children:t.teamName}),t.bridgeName&&e.jsx(Pt,{$variant:"bridge",children:t.bridgeName}),t.regionName&&e.jsx(Pt,{$variant:"region",children:t.regionName})]})]})]}),e.jsx(F,{title:f("machines:viewRepos"),children:e.jsx(Vt,{variant:"primary",icon:e.jsx(ae,{}),onClick:e=>{e.stopPropagation(),j(`/machines/${t.machineName}/repositories`,{state:{machine:t}})},children:f("machines:viewRepos")})})]},t.machineName))]},n)})})})(),e.jsx(Fe,{open:M.isOpen,onCancel:M.close,entityType:M.entityType,entityIdentifier:M.entityIdentifier,entityName:M.entityName}),I.state.data&&e.jsx(Ae,{open:I.isOpen,onCancel:I.close,machineName:I.state.data.machineName,teamName:I.state.data.teamName,bridgeName:I.state.data.bridgeName,onQueueItemCreated:g}),T.state.data&&e.jsx(Ge,{open:T.isOpen,machine:T.state.data,onCancel:T.close,onSuccess:()=>{T.close(),ce()}}),e.jsx(Ge,{open:A,machines:re.filter(e=>$.includes(e.machineName)),onCancel:()=>D(!1),onSuccess:()=>{D(!1),S([]),ce()}}),e.jsx(We,{open:R,machines:re.filter(e=>$.includes(e.machineName)),onCancel:()=>V(!1),onSuccess:()=>{V(!1),S([]),ce()}}),e.jsx(_e,{open:O,machines:re.filter(e=>$.includes(e.machineName)),onCancel:()=>G(!1)}),!x&&e.jsx(Ve,{machine:_,visible:ne,onClose:ye})]})},Wt=j.div`
  display: flex;
  height: 100%;
  width: 100%;
  position: relative;
  overflow: hidden;
`,_t=j.div`
  width: ${({$width:e})=>e};
  height: 100%;
  overflow: auto;
  min-width: ${({theme:e})=>e.dimensions.SPLIT_PANEL_MIN_WIDTH}px;
  transition: width 0.3s ease-in-out;
`,Bt=j.div`
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
`,Qt=t=>{const{type:i,selectedResource:n,onResourceSelect:s,isPanelCollapsed:r=!0,onTogglePanelCollapse:o}=t,c=Pe(),[m,l]=a.useState(c),[d,u]=a.useState(!1),[h,p]=a.useState(!1);a.useEffect(()=>{l(c)},[c]),a.useEffect(()=>{if(!n){u(!1);const e=setTimeout(()=>{p(!1)},250);return()=>clearTimeout(e)}p(!0),requestAnimationFrame(()=>{u(!0)})},[n]);const g=e=>{s(e)},x=()=>{s(null)},y=r?Oe.COLLAPSED_WIDTH:m;if("machine"===i){const a=n?`calc(100% - ${y}px)`:"100%";return e.jsxs(Wt,{"data-testid":"split-resource-view-container",children:[e.jsx(_t,{$width:a,"data-testid":"split-resource-view-left-panel",children:e.jsx(Gt,{...t,onRowClick:g,selectedMachine:n})}),h&&e.jsx(Bt,{$visible:d,$rightOffset:y,onClick:x,"data-testid":"split-resource-view-backdrop"}),n&&e.jsx(Le,{type:"machineName"in n?"machine":"repositoryName"in n?"repository":"container",data:n,visible:!0,onClose:x,splitWidth:m,onSplitWidthChange:l,isCollapsed:r,onToggleCollapse:o,collapsedWidth:Oe.COLLAPSED_WIDTH})]})}return null},Xt=j(ge)`
  && {
    padding: ${({theme:e})=>e.spacing.LG}px 0;
  }
`,qt=j(ye)`
  && {
    width: 100%;
  }
`,Ut=()=>{const{t:t}=Ee(["resources","machines","common"]),[n,h]=xe.useModal(),f=s(),j=i(),{teams:b,selectedTeams:v,setSelectedTeams:N,isLoading:k}=fe(),{modalState:C,currentResource:w,openModal:$,closeModal:S}=je("machine"),[M,I]=a.useState(null),[T,A]=a.useState(null),[D,R]=a.useState(null),[V,P]=a.useState(!0),[O,z]=a.useState({}),{state:G,open:W,close:_}=ie(),B=U(),{data:Q=[],refetch:X}=r(v.length>0?v:void 0,v.length>0),{data:q=[]}=o(v.length>0?v:void 0),{data:H=[]}=p(v.length>0?v:void 0),K=c(),Z=m(),J=l(),Y=d(),ee=u(),{executeAction:te,isExecuting:ae}=Ne();a.useEffect(()=>{const e=f.state;e?.createRepository&&j("/credentials",{state:e,replace:!0})},[f,j]);const pe=e=>{I(e),e&&(A(null),R(null),P(!1))},ge=a.useCallback(e=>{Ye({modal:n,t:t,resourceType:"machine",resourceName:e.machineName,translationNamespace:"machines",onConfirm:()=>Y.mutateAsync({teamName:e.teamName,machineName:e.machineName}),onSuccess:()=>X()})},[Y,n,X,t]),ye=a.useCallback(async e=>{try{if("create"===C.mode){const{autoSetup:a,...i}=e;if(await K.mutateAsync(i),L("success",t("machines:createSuccess")),a)try{await new Promise(e=>setTimeout(e,500));const a=await te({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,functionName:"setup",params:{datastore_size:"95%",source:"apt-repo",rclone_source:"install-script",docker_source:"docker-repo",install_amd_driver:"auto",install_nvidia_driver:"auto"},priority:3,addedVia:"machine-creation-auto-setup",machineVault:e.vaultContent||"{}"});a.success&&(a.taskId?(L("info",t("machines:setupQueued")),W(a.taskId,e.machineName)):a.isQueued&&L("info",t("machines:setupQueuedForSubmission")))}catch{L("warning",t("machines:machineCreatedButSetupFailed"))}S(),X()}else if(w){const t=w.machineName,a=e.machineName;a&&a!==t&&await Z.mutateAsync({teamName:w.teamName,currentMachineName:t,newMachineName:a}),e.bridgeName&&e.bridgeName!==w.bridgeName&&await J.mutateAsync({teamName:w.teamName,machineName:a||t,newBridgeName:e.bridgeName});const i=e.vaultContent;i&&i!==w.vaultContent&&await ee.mutateAsync({teamName:w.teamName,machineName:a||t,vaultContent:i,vaultVersion:w.vaultVersion+1}),S(),X()}}catch{}},[S,K,w,te,W,X,t,C.mode,J,Z,ee]),be=a.useCallback(async(e,t)=>{if(w)try{await ee.mutateAsync({teamName:w.teamName,machineName:w.machineName,vaultContent:e,vaultVersion:t}),S(),X()}catch{}},[S,w,X,ee]),ve=a.useCallback(async e=>{if(w)try{const a=w.machineName,i=w.bridgeName,n=b.find(e=>e.teamName===w.teamName),s="string"==typeof e.params.repository?e.params.repository:void 0,r={teamName:w.teamName,machineName:a,bridgeName:i,functionName:e.function.name,params:e.params,priority:e.priority,addedVia:"machine-table",teamVault:n?.vaultContent||"{}",machineVault:w.vaultContent||"{}",vaultContent:"{}"};if(s){const e=q.find(e=>e.repositoryGuid===s);r.repositoryGuid=e?.repositoryGuid||s,r.vaultContent=e?.vaultContent||"{}"}if("pull"===e.function.name){const t="string"==typeof e.params.sourceType?e.params.sourceType:void 0,a="string"==typeof e.params.from?e.params.from:void 0;if("machine"===t&&a){const e=Q.find(e=>e.machineName===a);e?.vaultContent&&(r.sourceMachineVault=e.vaultContent)}if("storage"===t&&a){const e=H.find(e=>e.storageName===a);e?.vaultContent&&(r.sourceStorageVault=e.vaultContent)}}const o=await te(r);S(),o.success?o.taskId?(L("success",t("machines:queueItemCreated")),W(o.taskId,a)):o.isQueued&&L("info",t("resources:messages.highestPriorityQueued",{resourceType:"machine"})):L("error",o.error||t("resources:errors.failedToCreateQueueItem"))}catch{L("error",t("resources:errors.failedToCreateQueueItem"))}},[S,w,te,Q,W,q,H,t,b]),ke=a.useCallback(async(e,a)=>{const i=g[a];if(!i)return void L("error",t("resources:errors.functionNotFound"));const n={};i.params&&Object.entries(i.params).forEach(([e,t])=>{t.default&&(n[e]=t.default)});const s=b.find(t=>t.teamName===e.teamName),r={teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,functionName:a,params:n,priority:4,addedVia:"machine-table-quick",teamVault:s?.vaultContent||"{}",machineVault:e.vaultContent||"{}",vaultContent:"{}"};try{const a=await te(r);a.success?a.taskId?(L("success",t("machines:queueItemCreated")),W(a.taskId,e.machineName)):a.isQueued&&L("info",t("resources:messages.highestPriorityQueued",{resourceType:"machine"})):L("error",a.error||t("resources:errors.failedToCreateQueueItem")),z(t=>({...t,[e.machineName]:Date.now()}))}catch{L("error",t("resources:errors.failedToCreateQueueItem"))}},[te,W,t,b]),Ce=K.isPending||Z.isPending||J.isPending||ae,we=ee.isPending,$e=C.data??w??void 0;return e.jsxs(e.Fragment,{children:[e.jsx(ne,{children:e.jsxs(se,{children:[e.jsx(re,{level:3,children:t("machines:heading",{defaultValue:"Machines"})}),e.jsxs(oe,{children:[e.jsx(se,{children:e.jsxs(ce,{children:[e.jsx(me,{children:e.jsx(le,{children:e.jsx(qt,{"data-testid":"machines-team-selector",teams:b,selectedTeams:v,onChange:N,loading:k,placeholder:t("teams.selectTeamToView")})})}),v.length>0&&e.jsxs(de,{children:[e.jsx(F,{title:t("machines:createMachine"),children:e.jsx(E,{iconOnly:!0,icon:e.jsx(ue,{}),"data-testid":"machines-create-machine-button",onClick:()=>$("create"),"aria-label":t("machines:createMachine")})}),e.jsx(F,{title:t("machines:connectivityTest"),children:e.jsx(E,{iconOnly:!0,icon:e.jsx(Ie,{}),"data-testid":"machines-connectivity-test-button",onClick:()=>B.open(),disabled:0===Q.length,"aria-label":t("machines:connectivityTest")})}),e.jsx(F,{title:t("common:actions.refresh"),children:e.jsx(E,{iconOnly:!0,icon:e.jsx(et,{}),"data-testid":"machines-refresh-button",onClick:()=>{X(),z(e=>({...e,_global:Date.now()}))},"aria-label":t("common:actions.refresh")})})]})]})}),e.jsx(he,{children:0===v.length?e.jsx(Xt,{image:Xt.PRESENTED_IMAGE_SIMPLE,description:t("teams.selectTeamPrompt")}):e.jsx(Qt,{type:"machine",teamFilter:v,showFilters:!0,showActions:!0,onCreateMachine:()=>$("create"),onEditMachine:e=>$("edit",e),onVaultMachine:e=>$("vault",e),onFunctionsMachine:(e,t)=>{t?ke(e,t):$("create",e)},onDeleteMachine:ge,enabled:v.length>0,refreshKeys:O,onQueueItemCreated:(e,t)=>{W(e,t)},selectedResource:M||T||D,onResourceSelect:e=>{e&&"machineName"in e?pe(e):e&&"repositoryName"in e?(pe(null),A(e),R(null),P(!1)):e&&"id"in e&&"state"in e?(pe(null),A(null),R(e),P(!1)):(pe(null),A(null),R(null))},isPanelCollapsed:V,onTogglePanelCollapse:()=>{P(e=>!e)}})})]})]})}),e.jsx(x,{"data-testid":"machines-machine-modal",open:C.open,onCancel:S,resourceType:"machine",mode:C.mode,existingData:$e,teamFilter:v.length>0?v:void 0,preselectedFunction:C.preselectedFunction,onSubmit:async e=>{const t=e;await ye(t)},onUpdateVault:"edit"===C.mode?be:void 0,onFunctionSubmit:e=>ve(e),isSubmitting:Ce,isUpdatingVault:we,functionCategories:["machine","backup"],hiddenParams:[],defaultParams:{}}),e.jsx(y,{"data-testid":"machines-queue-trace-modal",taskId:G.taskId,open:G.open,onCancel:()=>{const e=G.machineName;_(),e&&z(t=>({...t,[e]:Date.now()})),X()}}),e.jsx(gt,{"data-testid":"machines-connectivity-test-modal",open:B.isOpen,onClose:B.close,machines:Q,teamFilter:v}),h]})};export{Ut as default};
