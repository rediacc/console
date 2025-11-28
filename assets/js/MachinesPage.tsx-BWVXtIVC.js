import{j as e,u as t}from"./chunk-DXoLy3RZ.js";import{r as a,j as i,R as n,u as s}from"./chunk-ZRs5Vi2W.js";import{B as r,M as o,g as c,h as l,i as m,j as d,k as u,l as h,d as p,b as g,s as x,m as y,D as f,C as b,H as j,n as v,o as N,p as k,q as $,T as w,G as C,I as S,t as M,f as I,R as T,w as R,P as A,x as E,y as D,z as V,A as F,F as P,J as O,K as L,N as z,O as G,Q as _,U as B}from"../index-BR9NOAob.js";import{R as W}from"./chunk-Hl6774bT.js";import{u as Q,W as H}from"./chunk-BAIhHXX_.js";import{u as X,a as q,F as U,U as K}from"./chunk-Dm7gxawq.js";import{Q as Z}from"./chunk-D7yaEbWI.js";import{S as J}from"./chunk-Qkel2ey7.js";import{C as Y}from"./chunk-CmKNHb51.js";import{u as ee}from"./chunk-BFtzdRgy.js";import{u as te,A as ae,a as ie}from"./chunk-BmvtnyWe.js";import{u as ne}from"./chunk-Bzg6UoBT.js";import{w as se,R as re}from"./chunk-C_CyUQ7a.js";import{c as oe,a as ce,b as le}from"./chunk-Ch67B_CR.js";import{d as me,m as de,a as ue,n as he}from"./chunk-m5fYU7UF.js";import{T as pe,S as ge,c as xe,P as ye,A as fe,d as be,o as je,E as ve,C as Ne,B as ke,F as $e,M as we}from"./chunk-2wWKRBEk.js";import{u as Ce}from"./chunk-BYo3s0jF.js";import{B as Se}from"./chunk-DUnps4HP.js";import{u as Me,a as Ie,b as Te,c as Re,d as Ae,e as Ee,f as De}from"./chunk-DpPon4Vg.js";import{A as Ve}from"./chunk-ClBLWbGn.js";import{M as Fe,u as Pe,D as Oe,U as Le}from"./chunk-DwA2mA77.js";import{M as ze,A as Ge,R as _e,V as Be}from"./chunk-D_B4X96J.js";import"./chunk-DZV5yM2-.js";import{g as We}from"./chunk-DYR6ZHxn.js";import{c as Qe,a as He}from"./chunk-CGMqqO40.js";import{D as Xe,E as qe,L as Ue}from"./chunk-CDWV1bBN.js";import{E as Ke}from"./chunk-C_qJ8g-o.js";import{F as Ze}from"./chunk-C6ysgPTC.js";import{u as Je}from"./chunk-BNvdSKJ_.js";import{u as Ye,T as et}from"./chunk-B_W1IY6X.js";import{c as tt}from"./chunk-CuddkD5i.js";import"./chunk-_auT2Wjb.js";import"./chunk-CALlPgAP.js";import"./chunk-CsH6Euia.js";import"./chunk-DHNFesEm.js";import"./chunk-DSAOoKp6.js";import"./chunk-DT6ECJzX.js";import"./chunk-BouGVkfe.js";import"./chunk-CNkek46g.js";import"./chunk-DrLQ8Dnz.js";import"./chunk-m5qZpoFZ.js";import"./chunk-DhpoEw86.js";import"./chunk-OXAhRc9c.js";import"./chunk-g0lDXUhQ.js";import"./chunk-D5uDbUqz.js";import"./chunk-YZLd2bcq.js";import"./chunk-C5swOb3g.js";import"./chunk-B2qKbLWd.js";import"./forkTokenService.ts-B2KkyiIE.js";import"./chunk-BXw3FM0T.js";function at(e){const{buildQueueVault:t}=Q();te();const i=ee(),{data:n}=ne(),s=a.useCallback(async e=>{try{const a=function(e,t){if(e.teamVault&&"{}"!==e.teamVault)return e.teamVault;const a=t?.find(t=>t.teamName===e.teamName);return a?.vaultContent||"{}"}(e,n),s=await async function(e,t,a){const i=4,n="Ping connectivity test",s="ping-service",r="{}";return a({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,functionName:"ping",params:{},priority:e.priority||i,description:e.description||n,addedVia:e.addedVia||s,machineVault:e.machineVault||r,teamVault:t,repositoryVault:e.repositoryVault||r})}(e,a,t),r=await async function(e,t,a){const i=4;return a.mutateAsync({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,queueVault:t,priority:e.priority||i})}(e,s,i);return{taskId:r?.taskId,success:!!r?.taskId||!!r?.isQueued}}catch(a){return{success:!1,error:a.message||"Failed to execute ping function"}}},[t,i,n]),r=a.useCallback(async(e,t)=>s({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,priority:t?.priority,description:t?.description,addedVia:t?.addedVia,machineVault:e.vaultContent||"{}"}),[s]),o=a.useCallback(async(e,t)=>{const a=await s(e);if(!a.success||!a.taskId)return a;const i=await se(a.taskId,t);return{...a,completionResult:i,success:i.success,error:i.success?void 0:i.message}},[s]),c=a.useCallback(async(e,t)=>o({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,priority:t?.priority,description:t?.description,addedVia:t?.addedVia,machineVault:e.vaultContent||"{}"},t?.timeout),[o]);return{executePing:s,executePingForMachine:r,executePingAndWait:o,executePingForMachineAndWait:c,waitForQueueItemCompletion:se,isLoading:i.isPending}}const{Text:it}=pe,nt=de`
  0% {
    opacity: 0.65;
  }
  50% {
    opacity: 1;
  }
  100% {
    opacity: 0.65;
  }
`,st=me(r)`
  .ant-modal-body {
    padding: ${({theme:e})=>e.spacing.XL}px;
  }
`,rt=me(o)`
  width: 100%;
`,ot=me(c)``,ct=me(ge)`
  && {
    display: inline-flex;
    align-items: center;
    gap: ${({theme:e})=>e.spacing.SM}px;
    font-size: ${({theme:e})=>e.fontSize.BASE}px;
    color: ${({theme:e})=>e.colors.textPrimary};

    .anticon {
      font-size: ${({theme:e})=>e.dimensions.ICON_MD}px;
    }
  }
`,lt=me(l)``,mt=me(m)`
  && {
    min-width: ${({theme:e})=>2*e.spacing.XXL}px;
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,dt=me(xe)`
  && {
    min-width: ${({theme:e})=>e.dimensions.CONTROL_HEIGHT}px;
    min-height: ${({theme:e})=>e.dimensions.CONTROL_HEIGHT}px;
    border-radius: ${({theme:e})=>e.borderRadius.LG}px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,ut=me.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XS}px;
`,ht=me(ye)`
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
`,pt=me(it)`
  && {
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    color: ${({theme:e})=>e.colors.textSecondary};
  }
`,gt=me(fe)`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.LG}px;
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,xt=me.div`
  padding: ${({theme:e})=>e.spacing.MD}px;
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
  background-color: ${({theme:e})=>e.colors.bgSecondary};
`,yt=me.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({theme:e})=>e.spacing.XL}px;
`,ft=me.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XS}px;
`,bt=me(it)`
  && {
    color: ${({theme:e})=>e.colors.textSecondary};
  }
`,jt=me(it)`
  && {
    color: ${({theme:e,$variant:t})=>"success"===t?e.colors.success:"error"===t?e.colors.error:e.colors.textPrimary};
    font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
  }
`,vt=me(d)`
  .status-testing td {
    animation: ${nt} ${({theme:e})=>e.transitions.SLOW};
    background-color: ${({theme:e})=>e.colors.primaryBg};
  }

  .status-success td {
    background-color: ${({theme:e})=>e.colors.bgSuccess};
  }

  .status-failed td {
    background-color: ${({theme:e})=>e.colors.bgError};
  }
`,Nt=me.div`
  display: inline-flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,kt=me(it)`
  && {
    font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
  }
`,$t=me.span`
  display: inline-flex;
  align-items: center;
  color: ${({theme:e,$variant:t})=>{switch(t){case"success":return e.colors.success;case"failed":return e.colors.error;case"testing":return e.colors.primary;default:return e.colors.textSecondary}}};

  .anticon {
    font-size: ${({theme:e})=>e.fontSize.LG}px;
  }
`,wt=me(be)`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.MD}px;
    border-color: ${({theme:e})=>e.colors.borderSecondary};
    color: ${({theme:e})=>e.colors.textPrimary};
    background-color: ${({theme:e})=>e.colors.bgSecondary};
  }
`;me(u)`
  && {
    text-transform: capitalize;
  }
`;const Ct=me(it)`
  && {
    color: ${({theme:e,$isError:t})=>t?e.colors.error:e.colors.textPrimary};
  }
`,St=({open:t,onClose:i,machines:n})=>{const{t:s}=Ce(["machines","common"]),[r,o]=a.useState([]),[c,l]=a.useState(!1),[m,d]=a.useState(0),[u,y]=a.useState(-1),{executePingForMachine:f,waitForQueueItemCompletion:b}=at();a.useEffect(()=>{if(t&&n.length>0){const e=n.map(e=>({machineName:e.machineName,teamName:e.teamName,bridgeName:e.bridgeName,status:"pending"}));o(e),d(0),y(-1)}},[t,n]);const j=e=>e.success?s("machines:connectionSuccessful"):"TIMEOUT"===e.status?s("machines:testTimeout"):e.message||s("machines:connectionFailed"),v=async(e,t)=>{const a=Date.now();o(e=>e.map((e,a)=>a===t?{...e,status:"testing",timestamp:(new Date).toISOString()}:e));try{const i=await f(e,{priority:4,description:"Connectivity test",addedVia:"connectivity-test"});if(!i.success||!i.taskId)throw new Error(i.error||"Failed to create test task");{o(e=>e.map((e,a)=>a===t?{...e,taskId:i.taskId}:e));const e=await b(i.taskId),n=Date.now()-a;o(a=>a.map((a,i)=>i===t?{...a,status:e.success?"success":"failed",message:j(e),duration:n}:a))}}catch(i){const e=i instanceof Error?i.message:"Failed to create test task",n=Date.now()-a;o(a=>a.map((a,i)=>i===t?{...a,status:"failed",message:e,duration:n}:a))}},N=oe({title:s("machines:team"),dataIndex:"teamName",key:"teamName",renderWrapper:t=>e.jsx(wt,{children:t})}),k=oe({title:s("machines:bridge"),dataIndex:"bridgeName",key:"bridgeName",renderWrapper:t=>e.jsx(wt,{children:t})}),$=ce({title:s("machines:status"),dataIndex:"status",key:"status",width:140,statusMap:{pending:{color:"default",label:s("machines:pending"),icon:e.jsx(g,{})},testing:{color:"blue",label:s("machines:testing"),icon:e.jsx(J,{spin:!0})},success:{color:"success",label:s("machines:connected"),icon:e.jsx(p,{})},failed:{color:"error",label:s("machines:failed"),icon:e.jsx(Y,{})}}}),w=oe({title:s("machines:message"),dataIndex:"message",key:"message",ellipsis:!0,renderText:e=>e||"-"}),C=[{title:s("machines:machineName"),dataIndex:"machineName",key:"machineName",render:(t,a)=>e.jsxs(Nt,{"data-testid":`connectivity-machine-${t}`,children:[e.jsx($t,{$variant:a.status,children:(()=>{switch(a.status){case"testing":return e.jsx(J,{spin:!0,"data-testid":`connectivity-status-icon-testing-${t}`});case"success":return e.jsx(p,{"data-testid":`connectivity-status-icon-success-${t}`});case"failed":return e.jsx(Y,{"data-testid":`connectivity-status-icon-failed-${t}`});default:return e.jsx(g,{"data-testid":`connectivity-status-icon-pending-${t}`})}})()}),e.jsx(kt,{children:t})]})},N,k,{...$,render:(t,a,i)=>e.jsx("span",{"data-testid":`connectivity-status-tag-${a.machineName}-${t}`,children:$.render?.(t,a,i)})},{title:s("machines:responseTime"),dataIndex:"duration",key:"duration",width:120,render:e=>e?e<1e3?`${e}ms`:`${(e/1e3).toFixed(1)}s`:"-"},{...w,render:(t,a,i)=>{if(!t)return w.render?.(t,a,i);const n=w.render?.(t,a,i);return e.jsx(Ct,{$isError:"failed"===a.status,children:n})}}];return e.jsx(st,{"data-testid":"connectivity-modal",title:e.jsxs(ct,{children:[e.jsx(H,{}),s("machines:connectivityTest")]}),open:t,onCancel:i,className:h.ExtraLarge,destroyOnHidden:!0,footer:e.jsxs(lt,{children:[e.jsx(mt,{type:"primary",icon:e.jsx(J,{}),onClick:async()=>{l(!0);for(let a=0;a<n.length;a++)y(a),d(Math.round(a/n.length*100)),await v(n[a],a);d(100),l(!1),y(-1);const e=r.filter(e=>"success"===e.status).length,t=r.filter(e=>"failed"===e.status).length;0===t?x("success",s("machines:allMachinesConnected",{count:e})):x("warning",s("machines:machinesConnectedWithFailures",{successCount:e,failedCount:t}))},disabled:c||0===n.length,loading:c,"data-testid":"connectivity-run-test-button",children:s(c?"machines:testing":"machines:runTest")}),e.jsx(je,{title:"Close",children:e.jsx(dt,{icon:e.jsx(Y,{}),onClick:i,"data-testid":"connectivity-close-button","aria-label":"Close"})})]}),children:e.jsx(rt,{children:e.jsxs(ot,{children:[c&&e.jsxs(ut,{"data-testid":"connectivity-progress-container",children:[e.jsx(ht,{percent:m,status:"active","data-testid":"connectivity-progress-bar"}),u>=0&&u<n.length&&e.jsx(pt,{"data-testid":"connectivity-progress-text",children:s("machines:testingMachine",{machineName:n[u].machineName})})]}),e.jsx(gt,{message:s("machines:connectivityTestDescription"),type:"info",showIcon:!0,icon:e.jsx(H,{}),"data-testid":"connectivity-info-alert"}),e.jsx(vt,{columns:C,dataSource:r,rowKey:"machineName",pagination:!1,scroll:{y:400},loading:0===n.length,rowClassName:e=>`status-${e.status}`,"data-testid":"connectivity-results-table"}),!c&&r.some(e=>"pending"!==e.status)&&e.jsx(xt,{"data-testid":"connectivity-summary-statistics",children:e.jsxs(yt,{children:[e.jsxs(ft,{"data-testid":"connectivity-total-machines",children:[e.jsxs(bt,{children:[s("machines:totalMachines"),":"]}),e.jsx(jt,{children:n.length})]}),e.jsxs(ft,{"data-testid":"connectivity-connected-count",children:[e.jsxs(bt,{children:[s("machines:connected"),":"]}),e.jsx(jt,{$variant:"success",children:r.filter(e=>"success"===e.status).length})]}),e.jsxs(ft,{"data-testid":"connectivity-failed-count",children:[e.jsxs(bt,{children:[s("machines:failed"),":"]}),e.jsx(jt,{$variant:"error",children:r.filter(e=>"failed"===e.status).length})]}),e.jsxs(ft,{"data-testid":"connectivity-average-response",children:[e.jsxs(bt,{children:[s("machines:averageResponse"),":"]}),e.jsx(jt,{children:(()=>{const e=r.filter(e=>"success"===e.status&&e.duration);if(0===e.length)return"-";const t=e.reduce((e,t)=>e+(t.duration||0),0)/e.length;return t<1e3?`${Math.round(t)}ms`:`${(t/1e3).toFixed(1)}s`})()})]})]})})]})})})},Mt={team:{background:"var(--color-success)",color:"var(--color-text-inverse)"},bridge:{background:"var(--color-primary)",color:"var(--color-text-inverse)"},region:{background:"var(--color-info)",color:"var(--color-text-inverse)"},repository:{background:"var(--color-secondary)",color:"var(--color-text-inverse)"},status:{background:"var(--color-warning)",color:"var(--color-text-inverse)"},grand:{background:"var(--color-secondary)",color:"var(--color-text-inverse)"}},It=me.div`
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: ${({theme:e})=>e.spacing.MD}px;

  .machine-table-row {
    cursor: pointer;
    transition: background-color 0.2s ease;
  }

  .machine-table-row:hover {
    background-color: var(--color-bg-hover);
  }

  .machine-table-row--selected {
    background-color: var(--color-bg-selected) !important;
  }
`,Tt=me.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
`,Rt=me.div`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
  padding: ${({theme:e})=>e.spacing.SM}px ${({theme:e})=>e.spacing.MD}px;
  background-color: var(--color-bg-secondary);
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border: 1px solid var(--color-border-secondary);
  gap: ${({theme:e})=>e.spacing.MD}px;
`,At=me.span`
  font-weight: 600;
  color: var(--color-text-primary);
`,Et=me.div`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
`,Dt=me(xe)`
  && {
    min-width: 42px;
    height: ${y.DIMENSIONS.CONTROL_HEIGHT_SM}px;
    border-radius: ${({theme:e})=>e.borderRadius.SM}px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
`,Vt=me.span`
  width: 1px;
  height: 24px;
  background-color: var(--color-border-secondary);
  margin: 0 ${({theme:e})=>e.spacing.SM}px;
`,Ft=me(ve).attrs({image:ve.PRESENTED_IMAGE_SIMPLE})`
  margin-top: ${({theme:e})=>e.spacing.XL}px;
`,Pt=me.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XL}px;
`,Ot=me(Ne)`
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
`,Lt=me.div`
  display: flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
  padding: ${({theme:e})=>e.spacing.XS}px 0;
`,zt=me.div`
  width: 4px;
  height: ${y.DIMENSIONS.ICON_XL}px;
  border-radius: ${({theme:e})=>e.borderRadius.SM}px;
  background-color: ${({$color:e})=>e||"var(--color-text-secondary)"};
`,Gt=me.span`
  font-size: 18px;
  font-weight: 700;
  color: var(--color-text-primary);
`,_t=me.span`
  font-size: 14px;
  color: var(--color-text-secondary);
`,Bt=me.div`
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
`,Wt=me.div`
  display: flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.LG}px;
`,Qt=me(f)`
  font-size: ${y.DIMENSIONS.ICON_MD}px;
  color: var(--color-primary);
`,Ht=me(Qt)`
  font-size: ${y.DIMENSIONS.ICON_LG}px;
`,Xt=me.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XS}px;
`,qt=me.span`
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
`,Ut=me(xe)`
  && {
    /* Maintain compact pill styling to mirror historical control surface */
    height: ${y.DIMENSIONS.CONTROL_HEIGHT_SM}px;
    border-radius: ${({theme:e})=>e.borderRadius.SM}px;
    display: inline-flex;
    align-items: center;
    gap: ${({theme:e})=>e.spacing.XS}px;
  }
`;me.span`
  font-size: 18px;
  color: ${({$status:e})=>{switch(e){case"online":return"var(--color-success)";case"offline":return"var(--color-text-tertiary)";default:return"var(--color-text-quaternary)"}}};
  display: inline-flex;
  align-items: center;
  justify-content: center;
`;const Kt=me(be)`
  && {
    border: none;
    border-radius: ${({theme:e})=>e.borderRadius.MD}px;
    font-weight: 500;
    display: inline-flex;
    align-items: center;
    gap: ${({theme:e})=>e.spacing.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.SM}px;
    line-height: 24px;
    background-color: ${({$variant:e})=>Mt[e].background};
    color: ${({$variant:e})=>Mt[e].color};
  }
`,Zt=me(Kt)`
  && {
    font-size: 16px;
    padding: 4px ${({theme:e})=>e.spacing.MD}px;
  }
`,Jt=me(ke)`
  && .ant-badge-count {
    background-color: ${({$isPositive:e})=>e?"var(--color-success)":"var(--color-border-secondary)"};
    color: ${({$isPositive:e})=>e?"var(--color-text-inverse)":"var(--color-text-secondary)"};
  }
`,Yt=({teamFilter:s,showActions:r=!0,className:o="",onEditMachine:c,onFunctionsMachine:l,onDeleteMachine:m,enabled:d=!0,onQueueItemCreated:u,onRowClick:h,selectedMachine:g})=>{const{t:R}=Ce(["machines","common","functions","resources"]),A=i(),E=t(e=>e.ui.uiMode),D="expert"===E,{executePingForMachineAndWait:V}=at(),F=a.useRef(null),[P,O]=a.useState("machine"),[L,z]=a.useState([]),G=N(),_=k(),B=k(),[W,Q]=a.useState(!1),[q,U]=a.useState(!1),[K,Z]=a.useState(!1),[J,Y]=a.useState(null),[ee,te]=a.useState(!1);n.useEffect(()=>{"simple"===E&&"machine"!==P&&O("machine")},[E,P]);const{data:ie=[],isLoading:ne,refetch:se}=Me(s,d),{data:me=[]}=Ie(s),de=((e,t={})=>{const{rowHeight:i=54,headerHeight:n=55,paginationHeight:s=64,containerOffset:r=32,minRows:o=5,maxRows:c=100}=t,[l,m]=a.useState(10),d=a.useRef(null),u=a.useCallback(()=>{if(!e.current)return;const t=e.current.offsetHeight-n-s-r,a=Math.floor(t/i),l=Math.max(o,Math.min(c,a));m(l)},[e,i,n,s,r,o,c]),h=a.useRef(null);return a.useEffect(()=>(h.current=ue.debounce(u,300),()=>{h.current?.cancel()}),[u]),a.useEffect(()=>(u(),e.current&&window.ResizeObserver&&(d.current=new ResizeObserver(()=>{h.current?.()}),d.current.observe(e.current)),()=>{d.current&&d.current.disconnect(),h.current?.cancel()}),[u,e]),l})(F,{containerOffset:170,minRows:5,maxRows:50}),he=ie,pe=e=>We(e,me.map(e=>({repositoryGuid:e.repositoryGuid,repositoryName:e.repositoryName,grandGuid:e.grandGuid}))),ye=a.useCallback(e=>{m&&m(e)},[m]),fe=a.useCallback(e=>{h?h(e):(Y(e),te(!0))},[h]),be=a.useCallback(()=>{te(!1),Y(null)},[]),{getFunctionsByCategory:ve}=X(),Ne=a.useMemo(()=>ve("machine").filter(e=>e&&!1!==e.showInMenu&&"mount"!==e.name&&"pull"!==e.name),[ve]),ke=D&&$.isEnabled("assignToCluster"),we=a.useCallback(e=>{e.open&&e.machine?B.open(e.machine):B.close()},[B]),Te=a.useCallback(e=>{e.open&&e.entityType&&e.entityIdentifier?G.open({entityType:e.entityType,entityIdentifier:e.entityIdentifier,entityName:e.entityName}):G.close()},[G]),Re=n.useMemo(()=>(({t:t,isExpertMode:a,uiMode:i,showActions:n,hasSplitView:s,canAssignToCluster:r,onEditMachine:o,onFunctionsMachine:c,handleDelete:l,handleRowClick:m,executePingForMachineAndWait:d,setAssignClusterModal:u,setAuditTraceModal:h,machineFunctions:g})=>{const f=[],N=oe({title:t("machines:machineName"),dataIndex:"machineName",key:"machineName",maxLength:50,sorter:Qe("machineName"),renderWrapper:t=>e.jsxs(ge,{children:[e.jsx(Qt,{}),e.jsx("strong",{children:t})]})});return f.push(ce({title:t("machines:status"),dataIndex:"vaultStatusTime",key:"status",statusMap:{online:{icon:e.jsx(p,{}),label:t("machines:connected"),color:"success"},offline:{icon:e.jsx(Xe,{}),label:t("machines:connectionFailed"),color:"error"},unknown:{icon:e.jsx(Xe,{}),label:t("machines:statusUnknown"),color:"default"}},sorter:He(e=>{if(!e.vaultStatusTime)return 1/0;const t=new Date(e.vaultStatusTime+"Z");return((new Date).getTime()-t.getTime())/6e4<=3?0:1}),renderValue:(e,t)=>{if(!t.vaultStatusTime)return"unknown";const a=new Date(t.vaultStatusTime+"Z");return((new Date).getTime()-a.getTime())/6e4<=3?"online":"offline"}}),N),s||f.push(oe({title:t("machines:team"),dataIndex:"teamName",key:"teamName",width:150,sorter:Qe("teamName"),renderWrapper:t=>e.jsx(Kt,{$variant:"team",children:t})})),s||(a?f.push(oe({title:t("machines:region"),dataIndex:"regionName",key:"regionName",width:150,sorter:Qe("regionName"),renderText:e=>e||"-",renderWrapper:(t,a)=>"-"===a?e.jsx("span",{children:"-"}):e.jsx(Kt,{$variant:"region",children:t})}),oe({title:t("machines:bridge"),dataIndex:"bridgeName",key:"bridgeName",width:150,sorter:Qe("bridgeName"),renderWrapper:t=>e.jsx(Kt,{$variant:"bridge",children:t})})):"simple"!==i&&f.push(oe({title:t("bridges.bridge"),dataIndex:"bridgeName",key:"bridgeName",width:150,sorter:Qe("bridgeName"),renderWrapper:t=>e.jsx(Kt,{$variant:"bridge",children:t})}))),!s&&r&&f.push({title:t("machines:assignmentStatus.title"),key:"assignmentStatus",width:180,ellipsis:!0,render:(t,a)=>e.jsx(ze,{machine:a})}),s||f.push({title:t("machines:queueItems"),dataIndex:"queueCount",key:"queueCount",width:100,align:"center",sorter:Qe("queueCount"),render:t=>e.jsx(Jt,{$isPositive:t>0,count:t,showZero:!0})}),n&&f.push(le({title:t("common:table.actions"),width:y.DIMENSIONS.CARD_WIDTH,renderActions:a=>e.jsx(ae,{buttons:[{type:"view",icon:e.jsx(qe,{}),tooltip:"common:viewDetails",onClick:()=>m(a),variant:"default",testIdSuffix:"view-details"},{type:"edit",icon:e.jsx(Ke,{}),tooltip:"common:actions.edit",onClick:()=>o?.(a)},{type:"remote",icon:e.jsx(Ze,{}),tooltip:"machines:remote",dropdownItems:[{key:"functions",label:t("machines:runAction"),icon:e.jsx(Ze,{}),children:[...g.filter(e=>!1!==e?.showInMenu).map(t=>({key:`function-${t?.name||"unknown"}`,label:e.jsx("span",{title:t?.description||"",children:t?.name||"Unknown"}),onClick:()=>c?.(a,t?.name)})),{type:"divider"},{key:"advanced",label:t("machines:advanced"),icon:e.jsx(Ze,{}),onClick:()=>c?.(a)}]},{key:"test",label:t("machines:connectivityTest"),icon:e.jsx(H,{}),onClick:async()=>{x("info",t("machines:testingConnection"));const e=await d(a,{priority:4,description:"Connectivity test",addedVia:"machine-table",timeout:15e3});e.success?x("success",t("machines:connectionSuccessful")):x("error",e.error||t("machines:connectionFailed"))}},...r?[{key:"assignCluster",label:a.distributedStorageClusterName?t("machines:changeClusterAssignment"):t("machines:assignToCluster"),icon:e.jsx(b,{}),onClick:()=>u({open:!0,machine:a})}]:[]]},{type:"trace",icon:e.jsx(j,{}),tooltip:"machines:trace",onClick:()=>h({open:!0,entityType:"Machine",entityIdentifier:a.machineName,entityName:a.machineName})},{type:"delete",icon:e.jsx(v,{}),tooltip:"common:actions.delete",onClick:()=>l(a),danger:!0},{type:"custom",render:t=>e.jsx(Ue,{machine:t.machineName,teamName:t.teamName})}],record:a,idField:"machineName",testIdPrefix:"machine",t:t})})),f})({t:R,isExpertMode:D,uiMode:E,showActions:r,hasSplitView:Boolean(h),canAssignToCluster:ke,onEditMachine:c,onFunctionsMachine:l,handleDelete:ye,handleRowClick:fe,executePingForMachineAndWait:V,setAssignClusterModal:we,setAuditTraceModal:Te,machineFunctions:Ne}),[R,D,E,r,h,ke,c,l,ye,fe,V,we,Te,Ne]),Ae=ke?{selectedRowKeys:L,onChange:e=>{z(e)},getCheckboxProps:e=>({disabled:!1,"data-testid":`machine-checkbox-${e.machineName}`})}:void 0,Ee=a.useMemo(()=>{const e={};return"machine"===P||he.forEach(t=>{let a="";if("bridge"===P)a=t.bridgeName;else if("team"===P)a=t.teamName;else if("region"===P)a=t.regionName||"Unknown";else{if("repository"===P){const a=pe(t);if(0===a.length)return;return void a.forEach(a=>{const i=a.name;e[i]||(e[i]=[]),e[i].find(e=>e.machineName===t.machineName)||e[i].push(t)})}if("status"===P){const e=pe(t);if(0===e.length)a="No Repositories";else{const t=e.some(e=>!e.accessible),i=e.some(e=>e.mounted&&e.docker_running),n=e.some(e=>e.mounted&&!e.docker_running),s=e.some(e=>!e.mounted);a=t?"Inaccessible":i?"Active (Running)":n?"Ready (Stopped)":s?"Not Mounted":"Unknown Status"}}else if("grand"===P){const a=pe(t);if(0===a.length)return;return void a.forEach(a=>{let i="No Grand Repository";if(a.grandGuid){const e=me.find(e=>e.repositoryGuid===a.grandGuid);e&&(i=e.repositoryName)}e[i]||(e[i]=[]),e[i].find(e=>e.machineName===t.machineName)||e[i].push(t)})}}a&&(e[a]||(e[a]=[]),e[a].push(t))}),e},[he,P,me,pe]);return e.jsxs(It,{className:o,children:["simple"===E?null:e.jsx(Et,{children:e.jsxs(ge,{wrap:!0,size:"small",children:[e.jsx(je,{title:R("machines:machine"),children:e.jsx(Dt,{type:"machine"===P?"primary":"default",icon:e.jsx(f,{}),onClick:()=>O("machine"),"data-testid":"machine-view-toggle-machine","aria-label":R("machines:machine")})}),e.jsx(Vt,{}),e.jsx(je,{title:R("machines:groupByBridge"),children:e.jsx(Dt,{type:"bridge"===P?"primary":"default",icon:e.jsx(b,{}),onClick:()=>O("bridge"),"data-testid":"machine-view-toggle-bridge","aria-label":R("machines:groupByBridge")})}),e.jsx(je,{title:R("machines:groupByTeam"),children:e.jsx(Dt,{type:"team"===P?"primary":"default",icon:e.jsx(w,{}),onClick:()=>O("team"),"data-testid":"machine-view-toggle-team","aria-label":R("machines:groupByTeam")})}),D&&e.jsx(je,{title:R("machines:groupByRegion"),children:e.jsx(Dt,{type:"region"===P?"primary":"default",icon:e.jsx(C,{}),onClick:()=>O("region"),"data-testid":"machine-view-toggle-region","aria-label":R("machines:groupByRegion")})}),e.jsx(je,{title:R("machines:groupByRepository"),children:e.jsx(Dt,{type:"repository"===P?"primary":"default",icon:e.jsx(S,{}),onClick:()=>O("repository"),"data-testid":"machine-view-toggle-repository","aria-label":R("machines:groupByRepository")})}),e.jsx(je,{title:R("machines:groupByStatus"),children:e.jsx(Dt,{type:"status"===P?"primary":"default",icon:e.jsx(M,{}),onClick:()=>O("status"),"data-testid":"machine-view-toggle-status","aria-label":R("machines:groupByStatus")})}),e.jsx(je,{title:R("machines:groupByGrand"),children:e.jsx(Dt,{type:"grand"===P?"primary":"default",icon:e.jsx(Se,{}),onClick:()=>O("grand"),"data-testid":"machine-view-toggle-grand","aria-label":R("machines:groupByGrand")})})]})}),ke&&0!==L.length?e.jsxs(Rt,{children:[e.jsxs(ge,{size:"middle",children:[e.jsx(At,{children:R("machines:bulkActions.selected",{count:L.length})}),e.jsx(je,{title:R("common:actions.clearSelection"),children:e.jsx(xe,{size:"small",onClick:()=>z([]),"data-testid":"machine-bulk-clear-selection","aria-label":R("common:actions.clearSelection")})})]}),e.jsxs(ge,{size:"middle",children:[e.jsx(je,{title:R("machines:bulkActions.assignToCluster"),children:e.jsx(xe,{type:"primary",icon:e.jsx(b,{}),onClick:()=>Q(!0),"data-testid":"machine-bulk-assign-cluster","aria-label":R("machines:bulkActions.assignToCluster")})}),e.jsx(je,{title:R("machines:bulkActions.removeFromCluster"),children:e.jsx(xe,{icon:e.jsx(b,{}),onClick:()=>U(!0),"data-testid":"machine-bulk-remove-cluster","aria-label":R("machines:bulkActions.removeFromCluster")})}),e.jsx(je,{title:R("machines:bulkActions.viewAssignmentStatus"),children:e.jsx(xe,{icon:e.jsx(I,{}),onClick:()=>Z(!0),"data-testid":"machine-bulk-view-status","aria-label":R("machines:bulkActions.viewAssignmentStatus")})})]})]}):null,"machine"===P?e.jsx(Tt,{ref:F,children:e.jsx($e,{columns:Re,dataSource:he,rowKey:"machineName",loading:ne,scroll:{x:"max-content"},rowSelection:Ae,rowClassName:e=>{const t="machine-table-row";return g?.machineName===e.machineName?`${t} machine-table-row--selected`:t},"data-testid":"machine-table",pagination:{pageSize:de,showSizeChanger:!1,showTotal:(e,t)=>R("common:table.showingRecords",{start:t[0],end:t[1],total:e})},onRow:e=>({"data-testid":`machine-row-${e.machineName}`,onClick:t=>{const a=t.target;a.closest("button")||a.closest(".ant-dropdown")||a.closest(".ant-dropdown-menu")||A(`/machines/${e.machineName}/repositories`,{state:{machine:e}})}}),sticky:!0})}):(()=>{if(0===Object.keys(Ee).length)return e.jsx(Ft,{description:R("resources:repositories.noRepositories")});const t={machine:"repository",bridge:"bridge",team:"team",region:"region",repository:"repository",status:"status",grand:"grand"},a={team:"var(--color-success)",bridge:"var(--color-primary)",region:"var(--color-info)",repository:"var(--color-secondary)",status:"var(--color-warning)",grand:"var(--color-secondary)"},i={bridge:e.jsx(b,{}),team:e.jsx(w,{}),region:e.jsx(C,{}),repository:e.jsx(S,{}),status:e.jsx(M,{}),grand:e.jsx(Se,{})};return e.jsx(Pt,{children:Object.entries(Ee).map(([n,s],r)=>{const o=t[P],c=a[o];return e.jsxs(Ot,{$isAlternate:r%2==0,children:[e.jsxs(Lt,{children:[e.jsx(zt,{$color:c}),e.jsxs(ge,{size:"small",children:[e.jsxs(Gt,{children:["#",r+1]}),e.jsx(Zt,{$variant:o,icon:i[P],children:n}),e.jsxs(_t,{children:[s.length," ",1===s.length?R("machines:machine"):R("machines:machines")]})]})]}),s.map((t,a)=>e.jsxs(Bt,{$isStriped:a%2!=0,onClick:()=>A(`/machines/${t.machineName}/repositories`,{state:{machine:t}}),"data-testid":`grouped-machine-row-${t.machineName}`,children:[e.jsxs(Wt,{children:[e.jsx(Ht,{}),e.jsxs(Xt,{children:[e.jsx(qt,{children:t.machineName}),e.jsxs(ge,{size:"small",children:[e.jsx(Kt,{$variant:"team",children:t.teamName}),t.bridgeName&&e.jsx(Kt,{$variant:"bridge",children:t.bridgeName}),t.regionName&&e.jsx(Kt,{$variant:"region",children:t.regionName})]})]})]}),e.jsx(je,{title:R("machines:viewRepositories"),children:e.jsx(Ut,{type:"primary",icon:e.jsx(T,{}),onClick:e=>{e.stopPropagation(),A(`/machines/${t.machineName}/repositories`,{state:{machine:t}})},children:R("machines:viewRepositories")})})]},t.machineName))]},n)})})})(),e.jsx(Ve,{open:G.isOpen,onCancel:G.close,entityType:G.entityType,entityIdentifier:G.entityIdentifier,entityName:G.entityName}),_.state.data&&e.jsx(re,{open:_.isOpen,onCancel:_.close,machineName:_.state.data.machineName,teamName:_.state.data.teamName,bridgeName:_.state.data.bridgeName,onQueueItemCreated:u}),B.state.data&&e.jsx(Ge,{open:B.isOpen,machine:B.state.data,onCancel:B.close,onSuccess:()=>{B.close(),se()}}),e.jsx(Ge,{open:W,machines:ie.filter(e=>L.includes(e.machineName)),onCancel:()=>Q(!1),onSuccess:()=>{Q(!1),z([]),se()}}),e.jsx(_e,{open:q,machines:ie.filter(e=>L.includes(e.machineName)),onCancel:()=>U(!1),onSuccess:()=>{U(!1),z([]),se()}}),e.jsx(Be,{open:K,machines:ie.filter(e=>L.includes(e.machineName)),onCancel:()=>Z(!1)}),!h&&e.jsx(Fe,{machine:J,visible:ee,onClose:be})]})},ea=me.div`
  display: flex;
  height: 100%;
  width: 100%;
  position: relative;
  overflow: hidden;
`,ta=me.div`
  width: ${({$width:e})=>e};
  height: 100%;
  overflow: auto;
  min-width: 300px;
  transition: width 0.3s ease-in-out;
`,aa=me.div`
  position: fixed;
  top: 0;
  left: 0;
  right: ${({$rightOffset:e})=>`${e}px`};
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.4);
  opacity: ${({$visible:e})=>e?1:0};
  transition: opacity 250ms ease-in-out, right 0.3s ease-in-out;
  z-index: ${({theme:e})=>e.zIndex.MODAL};
  pointer-events: ${({$visible:e})=>e?"auto":"none"};
`,ia=t=>{const{type:i,selectedResource:n,onResourceSelect:s,isPanelCollapsed:r=!0,onTogglePanelCollapse:o}=t,c=Pe(),[l,m]=a.useState(c),[d,u]=a.useState(!1),[h,p]=a.useState(!1);a.useEffect(()=>{m(c)},[c]),a.useEffect(()=>{if(!n){u(!1);const e=setTimeout(()=>{p(!1)},250);return()=>clearTimeout(e)}p(!0),requestAnimationFrame(()=>{u(!0)})},[n]);const g=e=>{s(e)},x=()=>{s(null)},y=r?Oe.COLLAPSED_WIDTH:l;if("machine"===i){const a=n?`calc(100% - ${y}px)`:"100%";return e.jsxs(ea,{"data-testid":"split-resource-view-container",children:[e.jsx(ta,{$width:a,"data-testid":"split-resource-view-left-panel",children:e.jsx(Yt,{...t,onRowClick:g,selectedMachine:n})}),h&&e.jsx(aa,{$visible:d,$rightOffset:y,onClick:x,"data-testid":"split-resource-view-backdrop"}),n&&e.jsx(Le,{type:"machineName"in n?"machine":"repositoryName"in n?"repository":"container",data:n,visible:!0,onClose:x,splitWidth:l,onSplitWidthChange:m,isCollapsed:r,onToggleCollapse:o,collapsedWidth:Oe.COLLAPSED_WIDTH})]})}return null},na=()=>{const{t:t}=Ce(["resources","machines","common"]),[n,r]=we.useModal(),o=s(),c=i(),l=he(),{teams:m,selectedTeams:d,setSelectedTeams:u,isLoading:h}=Ye(),{modalState:p,currentResource:g,openModal:y,closeModal:f}=Je("machine"),[b,j]=a.useState(null),[v,N]=a.useState(null),[$,w]=a.useState(null),[C,S]=a.useState(!0),[M,I]=a.useState({}),{state:T,open:Q,close:X}=R(),J=k(),{data:Y=[],refetch:ee}=Me(d.length>0?d:void 0,d.length>0),{data:te=[]}=Ie(d.length>0?d:void 0),{data:ae=[]}=q(d.length>0?d:void 0),ne=Te(),se=Re(),re=Ae(),oe=Ee(),ce=De(),{executeAction:le,isExecuting:me}=ie();a.useEffect(()=>{const e=o.state;e?.createRepository&&c("/credentials",{state:e,replace:!0})},[o,c]);const de=e=>{j(e),e&&(N(null),w(null),S(!1))},ue=a.useCallback(e=>{tt({modal:n,t:t,resourceType:"machine",resourceName:e.machineName,translationNamespace:"machines",onConfirm:()=>oe.mutateAsync({teamName:e.teamName,machineName:e.machineName}),onSuccess:()=>ee()})},[oe,n,ee,t]),pe=a.useCallback(async e=>{try{if("create"===p.mode){const{autoSetup:i,...n}=e;if(await ne.mutateAsync(n),x("success",t("machines:createSuccess")),i)try{await new Promise(e=>setTimeout(e,500));const a=await le({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,functionName:"setup",params:{datastore_size:"95%",source:"apt-repo",rclone_source:"install-script",docker_source:"docker-repo",install_amd_driver:"auto",install_nvidia_driver:"auto"},priority:3,addedVia:"machine-creation-auto-setup",machineVault:e.machineVault||"{}"});a.success&&(a.taskId?(x("info",t("machines:setupQueued")),Q(a.taskId,e.machineName)):a.isQueued&&x("info",t("machines:setupQueuedForSubmission")))}catch(a){x("warning",t("machines:machineCreatedButSetupFailed"))}f(),ee()}else if(g){const t=g.machineName,a=e.machineName;a&&a!==t&&await se.mutateAsync({teamName:g.teamName,currentMachineName:t,newMachineName:a}),e.bridgeName&&e.bridgeName!==g.bridgeName&&await re.mutateAsync({teamName:g.teamName,machineName:a||t,newBridgeName:e.bridgeName});const i=e.machineVault;i&&i!==g.vaultContent&&await ce.mutateAsync({teamName:g.teamName,machineName:a||t,machineVault:i,vaultVersion:g.vaultVersion+1}),f(),ee()}}catch(a){}},[f,ne,g,le,Q,ee,t,p.mode,re,se,ce]),ge=a.useCallback(async(e,t)=>{if(g)try{await ce.mutateAsync({teamName:g.teamName,machineName:g.machineName,machineVault:e,vaultVersion:t}),f(),ee()}catch(a){}},[f,g,ee,ce]),xe=a.useCallback(async e=>{if(g)try{const a=g.machineName,i=g.bridgeName,n=m.find(e=>e.teamName===g.teamName),s={teamName:g.teamName,machineName:a,bridgeName:i,functionName:e.function.name,params:e.params,priority:e.priority,addedVia:"machine-table",teamVault:n?.vaultContent||"{}",machineVault:g.vaultContent||"{}"};if(e.params.repo){const t=te.find(t=>t.repositoryGuid===e.params.repo);s.repositoryGuid=t?.repositoryGuid||e.params.repo,s.repositoryVault=t?.vaultContent||"{}"}else s.repositoryVault="{}";if("pull"===e.function.name){if("machine"===e.params.sourceType&&e.params.from){const t=Y.find(t=>t.machineName===e.params.from);t?.vaultContent&&(s.sourceMachineVault=t.vaultContent)}if("storage"===e.params.sourceType&&e.params.from){const t=ae.find(t=>t.storageName===e.params.from);t?.vaultContent&&(s.sourceStorageVault=t.vaultContent)}}const r=await le(s);f(),r.success?r.taskId?(x("success",t("machines:queueItemCreated")),Q(r.taskId,a)):r.isQueued&&x("info",t("resources:messages.highestPriorityQueued",{resourceType:"machine"})):x("error",r.error||t("resources:errors.failedToCreateQueueItem"))}catch(a){x("error",t("resources:errors.failedToCreateQueueItem"))}},[f,g,le,Y,Q,te,ae,t,m]),ye=a.useCallback(async(e,a)=>{const i=U[a];if(!i)return void x("error",t("resources:errors.functionNotFound"));const n={};i.params&&Object.entries(i.params).forEach(([e,t])=>{t.default&&(n[e]=t.default)});const s=m.find(t=>t.teamName===e.teamName),r={teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,functionName:a,params:n,priority:4,addedVia:"machine-table-quick",teamVault:s?.vaultContent||"{}",machineVault:e.vaultContent||"{}",repositoryVault:"{}"};try{const a=await le(r);a.success?a.taskId?(x("success",t("machines:queueItemCreated")),Q(a.taskId,e.machineName)):a.isQueued&&x("info",t("resources:messages.highestPriorityQueued",{resourceType:"machine"})):x("error",a.error||t("resources:errors.failedToCreateQueueItem")),I(t=>({...t,[e.machineName]:Date.now()}))}catch(o){x("error",t("resources:errors.failedToCreateQueueItem"))}},[le,Q,t,m]),fe=ne.isPending||se.isPending||re.isPending||me,be=ce.isPending;return e.jsxs(e.Fragment,{children:[e.jsx(A,{children:e.jsxs(E,{children:[e.jsx(D,{level:3,children:t("machines:heading",{defaultValue:"Machines"})}),e.jsxs(V,{children:[e.jsx(F,{children:e.jsxs(P,{children:[e.jsx(O,{children:e.jsx(L,{children:e.jsx(et,{"data-testid":"machines-team-selector",teams:m,selectedTeams:d,onChange:u,loading:h,placeholder:t("teams.selectTeamToView"),style:{width:"100%"}})})}),d.length>0&&e.jsxs(z,{children:[e.jsx(je,{title:t("machines:createMachine"),children:e.jsx(G,{$variant:"primary",icon:e.jsx(_,{}),"data-testid":"machines-create-machine-button",onClick:()=>y("create"),"aria-label":t("machines:createMachine")})}),e.jsx(je,{title:t("machines:connectivityTest"),children:e.jsx(G,{icon:e.jsx(H,{}),"data-testid":"machines-connectivity-test-button",onClick:()=>J.open(),disabled:0===Y.length,"aria-label":t("machines:connectivityTest")})}),e.jsx(je,{title:t("common:actions.refresh"),children:e.jsx(G,{icon:e.jsx(W,{}),"data-testid":"machines-refresh-button",onClick:()=>{ee(),I(e=>({...e,_global:Date.now()}))},"aria-label":t("common:actions.refresh")})})]})]})}),e.jsx(B,{children:0===d.length?e.jsx(ve,{image:ve.PRESENTED_IMAGE_SIMPLE,description:t("teams.selectTeamPrompt"),style:{padding:`${l.spacing.LG}px 0`}}):e.jsx(ia,{type:"machine",teamFilter:d,showFilters:!0,showActions:!0,onCreateMachine:()=>y("create"),onEditMachine:e=>y("edit",e),onVaultMachine:e=>y("vault",e),onFunctionsMachine:(e,t)=>{t?ye(e,t):y("create",e)},onDeleteMachine:ue,enabled:d.length>0,refreshKeys:M,onQueueItemCreated:(e,t)=>{Q(e,t)},selectedResource:b||v||$,onResourceSelect:e=>{e&&"machineName"in e?de(e):e&&"repositoryName"in e?(de(null),N(e),w(null),S(!1)):e&&"id"in e&&"state"in e?(de(null),N(null),w(e),S(!1)):(de(null),N(null),w(null))},isPanelCollapsed:C,onTogglePanelCollapse:()=>{S(e=>!e)}})})]})]})}),e.jsx(K,{"data-testid":"machines-machine-modal",open:p.open,onCancel:f,resourceType:"machine",mode:p.mode,existingData:p.data||g,teamFilter:d.length>0?d:void 0,preselectedFunction:p.preselectedFunction,onSubmit:pe,onUpdateVault:"edit"===p.mode?ge:void 0,onFunctionSubmit:xe,isSubmitting:fe,isUpdatingVault:be,functionCategories:["machine","backup"],hiddenParams:[],defaultParams:{}}),e.jsx(Z,{"data-testid":"machines-queue-trace-modal",taskId:T.taskId,open:T.open,onCancel:()=>{const e=T.machineName;X(),e&&I(t=>({...t,[e]:Date.now()})),ee()}}),e.jsx(St,{"data-testid":"machines-connectivity-test-modal",open:J.isOpen,onClose:J.close,machines:Y,teamFilter:d}),r]})};export{na as default};
