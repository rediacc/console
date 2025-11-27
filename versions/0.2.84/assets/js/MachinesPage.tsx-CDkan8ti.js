import{j as e,u as t}from"./chunk-DXoLy3RZ.js";import{r as a,j as i,R as n,u as s}from"./chunk-ZRs5Vi2W.js";import{B as r,M as o,f as c,g as l,h as m,i as d,j as u,k as h,c as p,a as g,s as x,l as y,D as f,C as b,H as j,m as v,n as N,o as k,p as $,T as w,G as C,I as S,e as M,R as I,q as T,P as R,t as A,v as E,w as D,x as V,y as F,z as P,A as O,F as L,J as z,K as G,N as _}from"../index-7i0bsO_E.js";import{R as B}from"./chunk-Bw-nq2BR.js";import{u as W,W as H}from"./chunk-I7mT-8N_.js";import{u as Q,a as X,U as q}from"./chunk-CWW4BnTi.js";import{D as U,Q as K}from"./chunk-BDxbAu9o.js";import{S as Z}from"./chunk-CCbgn04V.js";import{C as J}from"./chunk-D6-ByJN2.js";import{u as Y}from"./chunk-hnCAaCuz.js";import{u as ee,A as te,a as ae}from"./chunk-DGo19EJ6.js";import{u as ie}from"./chunk-DMmxSnrV.js";import{w as ne,R as se}from"./chunk-Cp9V2mbo.js";import{c as re,a as oe,b as ce}from"./chunk-I9NhHZ_q.js";import{d as le,m as me,a as de,n as ue}from"./chunk-m5fYU7UF.js";import{T as he,S as pe,c as ge,P as xe,A as ye,d as fe,o as be,E as je,C as ve,B as Ne,F as ke,M as $e}from"./chunk-2wWKRBEk.js";import{u as we}from"./chunk-BYo3s0jF.js";import{B as Ce}from"./chunk-De-kZZqW.js";import{u as Se,a as Me,b as Ie,c as Te,d as Re,e as Ae,f as Ee}from"./chunk-CI0OFTiI.js";import{A as De}from"./chunk-WIb_BNXD.js";import{M as Ve,u as Fe,D as Pe,U as Oe}from"./chunk-Bap5ak2V.js";import{M as Le,A as ze,R as Ge,V as _e}from"./chunk-CdiN2ak6.js";import"./chunk-DZV5yM2-.js";import{g as Be}from"./chunk-DYR6ZHxn.js";import{c as We,a as He}from"./chunk-2c0p6Fl9.js";import{D as Qe,E as Xe,L as qe}from"./chunk-B1y6p5VZ.js";import{E as Ue}from"./chunk-CumuUmZU.js";import{F as Ke}from"./chunk-RxtBQV1G.js";import{u as Ze}from"./chunk-BNvdSKJ_.js";import{u as Je,T as Ye}from"./chunk-OenPMIAc.js";import{c as et}from"./chunk-DbBT9fKV.js";import"./chunk-_auT2Wjb.js";import"./chunk-CALlPgAP.js";import"./chunk-mNL_x99w.js";import"./chunk-ePHKCxmV.js";import"./chunk-bzdawvwX.js";import"./chunk-CxL3sOX5.js";import"./chunk-DcLruqvN.js";import"./chunk-BjDbc715.js";import"./chunk-DcH-rlk0.js";import"./chunk-C-B-RLh0.js";import"./chunk-DhpoEw86.js";import"./chunk-Dyq35-KQ.js";import"./chunk-D6fgw85G.js";import"./chunk-Trd_TFJk.js";import"./chunk-BJnhkI0H.js";import"./chunk-jEq3muhP.js";import"./chunk-mmvsq1hn.js";import"./forkTokenService.ts-MDK3HXEp.js";import"./chunk-X-ex5_IH.js";function tt(e){const{buildQueueVault:t}=W();ee();const i=Y(),{data:n}=ie(),s=a.useCallback(async e=>{try{const a=function(e,t){if(e.teamVault&&"{}"!==e.teamVault)return e.teamVault;const a=t?.find(t=>t.teamName===e.teamName);return a?.vaultContent||"{}"}(e,n),s=await async function(e,t,a){const i=4,n="Ping connectivity test",s="ping-service",r="{}";return a({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,functionName:"ping",params:{},priority:e.priority||i,description:e.description||n,addedVia:e.addedVia||s,machineVault:e.machineVault||r,teamVault:t,repositoryVault:e.repositoryVault||r})}(e,a,t),r=await async function(e,t,a){const i=4;return a.mutateAsync({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,queueVault:t,priority:e.priority||i})}(e,s,i);return{taskId:r?.taskId,success:!!r?.taskId||!!r?.isQueued}}catch(a){return{success:!1,error:a.message||"Failed to execute ping function"}}},[t,i,n]),r=a.useCallback(async(e,t)=>s({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,priority:t?.priority,description:t?.description,addedVia:t?.addedVia,machineVault:e.vaultContent||"{}"}),[s]),o=a.useCallback(async(e,t)=>{const a=await s(e);if(!a.success||!a.taskId)return a;const i=await ne(a.taskId,t);return{...a,completionResult:i,success:i.success,error:i.success?void 0:i.message}},[s]),c=a.useCallback(async(e,t)=>o({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,priority:t?.priority,description:t?.description,addedVia:t?.addedVia,machineVault:e.vaultContent||"{}"},t?.timeout),[o]);return{executePing:s,executePingForMachine:r,executePingAndWait:o,executePingForMachineAndWait:c,waitForQueueItemCompletion:ne,isLoading:i.isPending}}const{Text:at}=he,it=me`
  0% {
    opacity: 0.65;
  }
  50% {
    opacity: 1;
  }
  100% {
    opacity: 0.65;
  }
`,nt=le(r)`
  .ant-modal-body {
    padding: ${({theme:e})=>e.spacing.XL}px;
  }
`,st=le(o)`
  width: 100%;
`,rt=le(c)``,ot=le(pe)`
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
`,ct=le(l)``,lt=le(m)`
  && {
    min-width: ${({theme:e})=>2*e.spacing.XXL}px;
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,mt=le(ge)`
  && {
    min-width: ${({theme:e})=>e.dimensions.CONTROL_HEIGHT}px;
    min-height: ${({theme:e})=>e.dimensions.CONTROL_HEIGHT}px;
    border-radius: ${({theme:e})=>e.borderRadius.LG}px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,dt=le.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XS}px;
`,ut=le(xe)`
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
`,ht=le(at)`
  && {
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    color: ${({theme:e})=>e.colors.textSecondary};
  }
`,pt=le(ye)`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.LG}px;
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,gt=le.div`
  padding: ${({theme:e})=>e.spacing.MD}px;
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
  background-color: ${({theme:e})=>e.colors.bgSecondary};
`,xt=le.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({theme:e})=>e.spacing.XL}px;
`,yt=le.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XS}px;
`,ft=le(at)`
  && {
    color: ${({theme:e})=>e.colors.textSecondary};
  }
`,bt=le(at)`
  && {
    color: ${({theme:e,$variant:t})=>"success"===t?e.colors.success:"error"===t?e.colors.error:e.colors.textPrimary};
    font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
  }
`,jt=le(d)`
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
`,vt=le.div`
  display: inline-flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,Nt=le(at)`
  && {
    font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
  }
`,kt=le.span`
  display: inline-flex;
  align-items: center;
  color: ${({theme:e,$variant:t})=>{switch(t){case"success":return e.colors.success;case"failed":return e.colors.error;case"testing":return e.colors.primary;default:return e.colors.textSecondary}}};

  .anticon {
    font-size: ${({theme:e})=>e.fontSize.LG}px;
  }
`,$t=le(fe)`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.MD}px;
    border-color: ${({theme:e})=>e.colors.borderSecondary};
    color: ${({theme:e})=>e.colors.textPrimary};
    background-color: ${({theme:e})=>e.colors.bgSecondary};
  }
`;le(u)`
  && {
    text-transform: capitalize;
  }
`;const wt=le(at)`
  && {
    color: ${({theme:e,$isError:t})=>t?e.colors.error:e.colors.textPrimary};
  }
`,Ct=({open:t,onClose:i,machines:n})=>{const{t:s}=we(["machines","common"]),[r,o]=a.useState([]),[c,l]=a.useState(!1),[m,d]=a.useState(0),[u,y]=a.useState(-1),{executePingForMachine:f,waitForQueueItemCompletion:b}=tt();a.useEffect(()=>{if(t&&n.length>0){const e=n.map(e=>({machineName:e.machineName,teamName:e.teamName,bridgeName:e.bridgeName,status:"pending"}));o(e),d(0),y(-1)}},[t,n]);const j=e=>e.success?s("machines:connectionSuccessful"):"TIMEOUT"===e.status?s("machines:testTimeout"):e.message||s("machines:connectionFailed"),v=async(e,t)=>{const a=Date.now();o(e=>e.map((e,a)=>a===t?{...e,status:"testing",timestamp:(new Date).toISOString()}:e));try{const i=await f(e,{priority:4,description:"Connectivity test",addedVia:"connectivity-test"});if(!i.success||!i.taskId)throw new Error(i.error||"Failed to create test task");{o(e=>e.map((e,a)=>a===t?{...e,taskId:i.taskId}:e));const e=await b(i.taskId),n=Date.now()-a;o(a=>a.map((a,i)=>i===t?{...a,status:e.success?"success":"failed",message:j(e),duration:n}:a))}}catch(i){const e=i instanceof Error?i.message:"Failed to create test task",n=Date.now()-a;o(a=>a.map((a,i)=>i===t?{...a,status:"failed",message:e,duration:n}:a))}},N=re({title:s("machines:team"),dataIndex:"teamName",key:"teamName",renderWrapper:t=>e.jsx($t,{children:t})}),k=re({title:s("machines:bridge"),dataIndex:"bridgeName",key:"bridgeName",renderWrapper:t=>e.jsx($t,{children:t})}),$=oe({title:s("machines:status"),dataIndex:"status",key:"status",width:140,statusMap:{pending:{color:"default",label:s("machines:pending"),icon:e.jsx(g,{})},testing:{color:"blue",label:s("machines:testing"),icon:e.jsx(Z,{spin:!0})},success:{color:"success",label:s("machines:connected"),icon:e.jsx(p,{})},failed:{color:"error",label:s("machines:failed"),icon:e.jsx(J,{})}}}),w=re({title:s("machines:message"),dataIndex:"message",key:"message",ellipsis:!0,renderText:e=>e||"-"}),C=[{title:s("machines:machineName"),dataIndex:"machineName",key:"machineName",render:(t,a)=>e.jsxs(vt,{"data-testid":`connectivity-machine-${t}`,children:[e.jsx(kt,{$variant:a.status,children:(()=>{switch(a.status){case"testing":return e.jsx(Z,{spin:!0,"data-testid":`connectivity-status-icon-testing-${t}`});case"success":return e.jsx(p,{"data-testid":`connectivity-status-icon-success-${t}`});case"failed":return e.jsx(J,{"data-testid":`connectivity-status-icon-failed-${t}`});default:return e.jsx(g,{"data-testid":`connectivity-status-icon-pending-${t}`})}})()}),e.jsx(Nt,{children:t})]})},N,k,{...$,render:(t,a,i)=>e.jsx("span",{"data-testid":`connectivity-status-tag-${a.machineName}-${t}`,children:$.render?.(t,a,i)})},{title:s("machines:responseTime"),dataIndex:"duration",key:"duration",width:120,render:e=>e?e<1e3?`${e}ms`:`${(e/1e3).toFixed(1)}s`:"-"},{...w,render:(t,a,i)=>{if(!t)return w.render?.(t,a,i);const n=w.render?.(t,a,i);return e.jsx(wt,{$isError:"failed"===a.status,children:n})}}];return e.jsx(nt,{"data-testid":"connectivity-modal",title:e.jsxs(ot,{children:[e.jsx(H,{}),s("machines:connectivityTest")]}),open:t,onCancel:i,className:h.ExtraLarge,destroyOnHidden:!0,footer:e.jsxs(ct,{children:[e.jsx(lt,{type:"primary",icon:e.jsx(Z,{}),onClick:async()=>{l(!0);for(let a=0;a<n.length;a++)y(a),d(Math.round(a/n.length*100)),await v(n[a],a);d(100),l(!1),y(-1);const e=r.filter(e=>"success"===e.status).length,t=r.filter(e=>"failed"===e.status).length;0===t?x("success",s("machines:allMachinesConnected",{count:e})):x("warning",s("machines:machinesConnectedWithFailures",{successCount:e,failedCount:t}))},disabled:c||0===n.length,loading:c,"data-testid":"connectivity-run-test-button",children:s(c?"machines:testing":"machines:runTest")}),e.jsx(be,{title:"Close",children:e.jsx(mt,{icon:e.jsx(J,{}),onClick:i,"data-testid":"connectivity-close-button","aria-label":"Close"})})]}),children:e.jsx(st,{children:e.jsxs(rt,{children:[c&&e.jsxs(dt,{"data-testid":"connectivity-progress-container",children:[e.jsx(ut,{percent:m,status:"active","data-testid":"connectivity-progress-bar"}),u>=0&&u<n.length&&e.jsx(ht,{"data-testid":"connectivity-progress-text",children:s("machines:testingMachine",{machineName:n[u].machineName})})]}),e.jsx(pt,{message:s("machines:connectivityTestDescription"),type:"info",showIcon:!0,icon:e.jsx(H,{}),"data-testid":"connectivity-info-alert"}),e.jsx(jt,{columns:C,dataSource:r,rowKey:"machineName",pagination:!1,scroll:{y:400},loading:0===n.length,rowClassName:e=>`status-${e.status}`,"data-testid":"connectivity-results-table"}),!c&&r.some(e=>"pending"!==e.status)&&e.jsx(gt,{"data-testid":"connectivity-summary-statistics",children:e.jsxs(xt,{children:[e.jsxs(yt,{"data-testid":"connectivity-total-machines",children:[e.jsxs(ft,{children:[s("machines:totalMachines"),":"]}),e.jsx(bt,{children:n.length})]}),e.jsxs(yt,{"data-testid":"connectivity-connected-count",children:[e.jsxs(ft,{children:[s("machines:connected"),":"]}),e.jsx(bt,{$variant:"success",children:r.filter(e=>"success"===e.status).length})]}),e.jsxs(yt,{"data-testid":"connectivity-failed-count",children:[e.jsxs(ft,{children:[s("machines:failed"),":"]}),e.jsx(bt,{$variant:"error",children:r.filter(e=>"failed"===e.status).length})]}),e.jsxs(yt,{"data-testid":"connectivity-average-response",children:[e.jsxs(ft,{children:[s("machines:averageResponse"),":"]}),e.jsx(bt,{children:(()=>{const e=r.filter(e=>"success"===e.status&&e.duration);if(0===e.length)return"-";const t=e.reduce((e,t)=>e+(t.duration||0),0)/e.length;return t<1e3?`${Math.round(t)}ms`:`${(t/1e3).toFixed(1)}s`})()})]})]})})]})})})},St={team:{background:"var(--color-success)",color:"var(--color-text-inverse)"},bridge:{background:"var(--color-primary)",color:"var(--color-text-inverse)"},region:{background:"var(--color-info)",color:"var(--color-text-inverse)"},repository:{background:"var(--color-secondary)",color:"var(--color-text-inverse)"},status:{background:"var(--color-warning)",color:"var(--color-text-inverse)"},grand:{background:"var(--color-secondary)",color:"var(--color-text-inverse)"}},Mt=le.div`
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
`,It=le.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
`,Tt=le.div`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
  padding: ${({theme:e})=>e.spacing.SM}px ${({theme:e})=>e.spacing.MD}px;
  background-color: var(--color-bg-secondary);
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border: 1px solid var(--color-border-secondary);
  gap: ${({theme:e})=>e.spacing.MD}px;
`,Rt=le.span`
  font-weight: 600;
  color: var(--color-text-primary);
`,At=le.div`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
`,Et=le(ge)`
  && {
    min-width: 42px;
    height: ${y.DIMENSIONS.CONTROL_HEIGHT_SM}px;
    border-radius: ${({theme:e})=>e.borderRadius.SM}px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
`,Dt=le.span`
  width: 1px;
  height: 24px;
  background-color: var(--color-border-secondary);
  margin: 0 ${({theme:e})=>e.spacing.SM}px;
`,Vt=le(je).attrs({image:je.PRESENTED_IMAGE_SIMPLE})`
  margin-top: ${({theme:e})=>e.spacing.XL}px;
`,Ft=le.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XL}px;
`,Pt=le(ve)`
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
`,Ot=le.div`
  display: flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
  padding: ${({theme:e})=>e.spacing.XS}px 0;
`,Lt=le.div`
  width: 4px;
  height: ${y.DIMENSIONS.ICON_XL}px;
  border-radius: ${({theme:e})=>e.borderRadius.SM}px;
  background-color: ${({$color:e})=>e||"var(--color-text-secondary)"};
`,zt=le.span`
  font-size: 18px;
  font-weight: 700;
  color: var(--color-text-primary);
`,Gt=le.span`
  font-size: 14px;
  color: var(--color-text-secondary);
`,_t=le.div`
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
`,Bt=le.div`
  display: flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.LG}px;
`,Wt=le(f)`
  font-size: ${y.DIMENSIONS.ICON_MD}px;
  color: var(--color-primary);
`,Ht=le(Wt)`
  font-size: ${y.DIMENSIONS.ICON_LG}px;
`,Qt=le.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XS}px;
`,Xt=le.span`
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
`,qt=le(ge)`
  && {
    /* Maintain compact pill styling to mirror historical control surface */
    height: ${y.DIMENSIONS.CONTROL_HEIGHT_SM}px;
    border-radius: ${({theme:e})=>e.borderRadius.SM}px;
    display: inline-flex;
    align-items: center;
    gap: ${({theme:e})=>e.spacing.XS}px;
  }
`;le.span`
  font-size: 18px;
  color: ${({$status:e})=>{switch(e){case"online":return"var(--color-success)";case"offline":return"var(--color-text-tertiary)";default:return"var(--color-text-quaternary)"}}};
  display: inline-flex;
  align-items: center;
  justify-content: center;
`;const Ut=le(fe)`
  && {
    border: none;
    border-radius: ${({theme:e})=>e.borderRadius.MD}px;
    font-weight: 500;
    display: inline-flex;
    align-items: center;
    gap: ${({theme:e})=>e.spacing.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.SM}px;
    line-height: 24px;
    background-color: ${({$variant:e})=>St[e].background};
    color: ${({$variant:e})=>St[e].color};
  }
`,Kt=le(Ut)`
  && {
    font-size: 16px;
    padding: 4px ${({theme:e})=>e.spacing.MD}px;
  }
`,Zt=le(Ne)`
  && .ant-badge-count {
    background-color: ${({$isPositive:e})=>e?"var(--color-success)":"var(--color-border-secondary)"};
    color: ${({$isPositive:e})=>e?"var(--color-text-inverse)":"var(--color-text-secondary)"};
  }
`,Jt=({teamFilter:s,showActions:r=!0,className:o="",onEditMachine:c,onFunctionsMachine:l,onDeleteMachine:m,enabled:d=!0,onQueueItemCreated:u,onRowClick:h,selectedMachine:g})=>{const{t:T}=we(["machines","common","functions","resources"]),R=i(),A=t(e=>e.ui.uiMode),E="expert"===A,{executePingForMachineAndWait:D}=tt(),V=a.useRef(null),[F,P]=a.useState("machine"),[O,L]=a.useState([]),z=N(),G=k(),_=k(),[B,W]=a.useState(!1),[X,q]=a.useState(!1),[K,Z]=a.useState(!1),[J,Y]=a.useState(null),[ee,ae]=a.useState(!1);n.useEffect(()=>{"simple"===A&&"machine"!==F&&P("machine")},[A,F]);const{data:ie=[],isLoading:ne,refetch:le}=Se(s,d),{data:me=[]}=Me(s),ue=((e,t={})=>{const{rowHeight:i=54,headerHeight:n=55,paginationHeight:s=64,containerOffset:r=32,minRows:o=5,maxRows:c=100}=t,[l,m]=a.useState(10),d=a.useRef(null),u=a.useCallback(()=>{if(!e.current)return;const t=e.current.offsetHeight-n-s-r,a=Math.floor(t/i),l=Math.max(o,Math.min(c,a));m(l)},[e,i,n,s,r,o,c]),h=a.useRef(null);return a.useEffect(()=>(h.current=de.debounce(u,300),()=>{h.current?.cancel()}),[u]),a.useEffect(()=>(u(),e.current&&window.ResizeObserver&&(d.current=new ResizeObserver(()=>{h.current?.()}),d.current.observe(e.current)),()=>{d.current&&d.current.disconnect(),h.current?.cancel()}),[u,e]),l})(V,{containerOffset:170,minRows:5,maxRows:50}),he=ie,xe=e=>Be(e,me.map(e=>({repositoryGuid:e.repositoryGuid,repositoryName:e.repositoryName,grandGuid:e.grandGuid}))),ye=a.useCallback(e=>{m&&m(e)},[m]),fe=a.useCallback(e=>{h?h(e):(Y(e),ae(!0))},[h]),je=a.useCallback(()=>{ae(!1),Y(null)},[]),{getFunctionsByCategory:ve}=Q(),Ne=a.useMemo(()=>ve("machine").filter(e=>e&&!1!==e.showInMenu&&"mount"!==e.name&&"pull"!==e.name),[ve]),$e=E&&$.isEnabled("assignToCluster"),Ie=a.useCallback(e=>{e.open&&e.machine?_.open(e.machine):_.close()},[_]),Te=a.useCallback(e=>{e.open&&e.entityType&&e.entityIdentifier?z.open({entityType:e.entityType,entityIdentifier:e.entityIdentifier,entityName:e.entityName}):z.close()},[z]),Re=n.useMemo(()=>(({t:t,isExpertMode:a,uiMode:i,showActions:n,hasSplitView:s,canAssignToCluster:r,onEditMachine:o,onFunctionsMachine:c,handleDelete:l,handleRowClick:m,executePingForMachineAndWait:d,setAssignClusterModal:u,setAuditTraceModal:h,machineFunctions:g})=>{const f=[],N=re({title:t("machines:machineName"),dataIndex:"machineName",key:"machineName",sorter:We("machineName"),renderWrapper:t=>e.jsxs(pe,{children:[e.jsx(Wt,{}),e.jsx("strong",{children:t})]})});return f.push(oe({title:t("machines:status"),dataIndex:"vaultStatusTime",key:"status",statusMap:{online:{icon:e.jsx(p,{}),label:t("machines:connected"),color:"success"},offline:{icon:e.jsx(Qe,{}),label:t("machines:connectionFailed"),color:"error"},unknown:{icon:e.jsx(Qe,{}),label:t("machines:statusUnknown"),color:"default"}},sorter:He(e=>{if(!e.vaultStatusTime)return 1/0;const t=new Date(e.vaultStatusTime+"Z");return((new Date).getTime()-t.getTime())/6e4<=3?0:1}),renderValue:(e,t)=>{if(!t.vaultStatusTime)return"unknown";const a=new Date(t.vaultStatusTime+"Z");return((new Date).getTime()-a.getTime())/6e4<=3?"online":"offline"}}),N),s||f.push(re({title:t("machines:team"),dataIndex:"teamName",key:"teamName",width:150,sorter:We("teamName"),renderWrapper:t=>e.jsx(Ut,{$variant:"team",children:t})})),s||(a?f.push(re({title:t("machines:region"),dataIndex:"regionName",key:"regionName",width:150,sorter:We("regionName"),renderText:e=>e||"-",renderWrapper:(t,a)=>"-"===a?e.jsx("span",{children:"-"}):e.jsx(Ut,{$variant:"region",children:t})}),re({title:t("machines:bridge"),dataIndex:"bridgeName",key:"bridgeName",width:150,sorter:We("bridgeName"),renderWrapper:t=>e.jsx(Ut,{$variant:"bridge",children:t})})):"simple"!==i&&f.push(re({title:t("bridges.bridge"),dataIndex:"bridgeName",key:"bridgeName",width:150,sorter:We("bridgeName"),renderWrapper:t=>e.jsx(Ut,{$variant:"bridge",children:t})}))),!s&&r&&f.push({title:t("machines:assignmentStatus.title"),key:"assignmentStatus",width:180,ellipsis:!0,render:(t,a)=>e.jsx(Le,{machine:a})}),s||f.push({title:t("machines:queueItems"),dataIndex:"queueCount",key:"queueCount",width:100,align:"center",sorter:We("queueCount"),render:t=>e.jsx(Zt,{$isPositive:t>0,count:t,showZero:!0})}),n&&f.push(ce({title:t("common:table.actions"),width:y.DIMENSIONS.CARD_WIDTH,renderActions:a=>e.jsx(te,{buttons:[{type:"view",icon:e.jsx(Xe,{}),tooltip:"common:viewDetails",onClick:()=>m(a),variant:"default",testIdSuffix:"view-details"},{type:"edit",icon:e.jsx(Ue,{}),tooltip:"common:actions.edit",onClick:()=>o?.(a)},{type:"remote",icon:e.jsx(Ke,{}),tooltip:"machines:remote",dropdownItems:[{key:"functions",label:t("machines:runAction"),icon:e.jsx(Ke,{}),children:[...g.filter(e=>!1!==e?.showInMenu).map(t=>({key:`function-${t?.name||"unknown"}`,label:e.jsx("span",{title:t?.description||"",children:t?.name||"Unknown"}),onClick:()=>c?.(a,t?.name)})),{type:"divider"},{key:"advanced",label:t("machines:advanced"),icon:e.jsx(Ke,{}),onClick:()=>c?.(a)}]},{key:"test",label:t("machines:connectivityTest"),icon:e.jsx(H,{}),onClick:async()=>{x("info",t("machines:testingConnection"));const e=await d(a,{priority:4,description:"Connectivity test",addedVia:"machine-table",timeout:15e3});e.success?x("success",t("machines:connectionSuccessful")):x("error",e.error||t("machines:connectionFailed"))}},...r?[{key:"assignCluster",label:a.distributedStorageClusterName?t("machines:changeClusterAssignment"):t("machines:assignToCluster"),icon:e.jsx(b,{}),onClick:()=>u({open:!0,machine:a})}]:[]]},{type:"trace",icon:e.jsx(j,{}),tooltip:"machines:trace",onClick:()=>h({open:!0,entityType:"Machine",entityIdentifier:a.machineName,entityName:a.machineName})},{type:"delete",icon:e.jsx(v,{}),tooltip:"common:actions.delete",onClick:()=>l(a),danger:!0},{type:"custom",render:t=>e.jsx(qe,{machine:t.machineName,teamName:t.teamName})}],record:a,idField:"machineName",testIdPrefix:"machine",t:t})})),f})({t:T,isExpertMode:E,uiMode:A,showActions:r,hasSplitView:Boolean(h),canAssignToCluster:$e,onEditMachine:c,onFunctionsMachine:l,handleDelete:ye,handleRowClick:fe,executePingForMachineAndWait:D,setAssignClusterModal:Ie,setAuditTraceModal:Te,machineFunctions:Ne}),[T,E,A,r,h,$e,c,l,ye,fe,D,Ie,Te,Ne]),Ae=$e?{selectedRowKeys:O,onChange:e=>{L(e)},getCheckboxProps:e=>({disabled:!1,"data-testid":`machine-checkbox-${e.machineName}`})}:void 0,Ee=a.useMemo(()=>{const e={};return"machine"===F||he.forEach(t=>{let a="";if("bridge"===F)a=t.bridgeName;else if("team"===F)a=t.teamName;else if("region"===F)a=t.regionName||"Unknown";else{if("repository"===F){const a=xe(t);if(0===a.length)return;return void a.forEach(a=>{const i=a.name;e[i]||(e[i]=[]),e[i].find(e=>e.machineName===t.machineName)||e[i].push(t)})}if("status"===F){const e=xe(t);if(0===e.length)a="No Repositories";else{const t=e.some(e=>!e.accessible),i=e.some(e=>e.mounted&&e.docker_running),n=e.some(e=>e.mounted&&!e.docker_running),s=e.some(e=>!e.mounted);a=t?"Inaccessible":i?"Active (Running)":n?"Ready (Stopped)":s?"Not Mounted":"Unknown Status"}}else if("grand"===F){const a=xe(t);if(0===a.length)return;return void a.forEach(a=>{let i="No Grand Repository";if(a.grandGuid){const e=me.find(e=>e.repositoryGuid===a.grandGuid);e&&(i=e.repositoryName)}e[i]||(e[i]=[]),e[i].find(e=>e.machineName===t.machineName)||e[i].push(t)})}}a&&(e[a]||(e[a]=[]),e[a].push(t))}),e},[he,F,me,xe]);return e.jsxs(Mt,{className:o,children:["simple"===A?null:e.jsx(At,{children:e.jsxs(pe,{wrap:!0,size:"small",children:[e.jsx(be,{title:T("machines:machine"),children:e.jsx(Et,{type:"machine"===F?"primary":"default",icon:e.jsx(f,{}),onClick:()=>P("machine"),"data-testid":"machine-view-toggle-machine","aria-label":T("machines:machine")})}),e.jsx(Dt,{}),e.jsx(be,{title:T("machines:groupByBridge"),children:e.jsx(Et,{type:"bridge"===F?"primary":"default",icon:e.jsx(b,{}),onClick:()=>P("bridge"),"data-testid":"machine-view-toggle-bridge","aria-label":T("machines:groupByBridge")})}),e.jsx(be,{title:T("machines:groupByTeam"),children:e.jsx(Et,{type:"team"===F?"primary":"default",icon:e.jsx(w,{}),onClick:()=>P("team"),"data-testid":"machine-view-toggle-team","aria-label":T("machines:groupByTeam")})}),E&&e.jsx(be,{title:T("machines:groupByRegion"),children:e.jsx(Et,{type:"region"===F?"primary":"default",icon:e.jsx(C,{}),onClick:()=>P("region"),"data-testid":"machine-view-toggle-region","aria-label":T("machines:groupByRegion")})}),e.jsx(be,{title:T("machines:groupByRepository"),children:e.jsx(Et,{type:"repository"===F?"primary":"default",icon:e.jsx(S,{}),onClick:()=>P("repository"),"data-testid":"machine-view-toggle-repository","aria-label":T("machines:groupByRepository")})}),e.jsx(be,{title:T("machines:groupByStatus"),children:e.jsx(Et,{type:"status"===F?"primary":"default",icon:e.jsx(U,{}),onClick:()=>P("status"),"data-testid":"machine-view-toggle-status","aria-label":T("machines:groupByStatus")})}),e.jsx(be,{title:T("machines:groupByGrand"),children:e.jsx(Et,{type:"grand"===F?"primary":"default",icon:e.jsx(Ce,{}),onClick:()=>P("grand"),"data-testid":"machine-view-toggle-grand","aria-label":T("machines:groupByGrand")})})]})}),$e&&0!==O.length?e.jsxs(Tt,{children:[e.jsxs(pe,{size:"middle",children:[e.jsx(Rt,{children:T("machines:bulkActions.selected",{count:O.length})}),e.jsx(be,{title:T("common:actions.clearSelection"),children:e.jsx(ge,{size:"small",onClick:()=>L([]),"data-testid":"machine-bulk-clear-selection","aria-label":T("common:actions.clearSelection")})})]}),e.jsxs(pe,{size:"middle",children:[e.jsx(be,{title:T("machines:bulkActions.assignToCluster"),children:e.jsx(ge,{type:"primary",icon:e.jsx(b,{}),onClick:()=>W(!0),"data-testid":"machine-bulk-assign-cluster","aria-label":T("machines:bulkActions.assignToCluster")})}),e.jsx(be,{title:T("machines:bulkActions.removeFromCluster"),children:e.jsx(ge,{icon:e.jsx(b,{}),onClick:()=>q(!0),"data-testid":"machine-bulk-remove-cluster","aria-label":T("machines:bulkActions.removeFromCluster")})}),e.jsx(be,{title:T("machines:bulkActions.viewAssignmentStatus"),children:e.jsx(ge,{icon:e.jsx(M,{}),onClick:()=>Z(!0),"data-testid":"machine-bulk-view-status","aria-label":T("machines:bulkActions.viewAssignmentStatus")})})]})]}):null,"machine"===F?e.jsx(It,{ref:V,children:e.jsx(ke,{columns:Re,dataSource:he,rowKey:"machineName",loading:ne,scroll:{x:"max-content"},rowSelection:Ae,rowClassName:e=>{const t="machine-table-row";return g?.machineName===e.machineName?`${t} machine-table-row--selected`:t},"data-testid":"machine-table",pagination:{pageSize:ue,showSizeChanger:!1,showTotal:(e,t)=>T("common:table.showingRecords",{start:t[0],end:t[1],total:e})},onRow:e=>({"data-testid":`machine-row-${e.machineName}`,onClick:t=>{const a=t.target;a.closest("button")||a.closest(".ant-dropdown")||a.closest(".ant-dropdown-menu")||R(`/machines/${e.machineName}/repositories`,{state:{machine:e}})}}),sticky:!0})}):(()=>{if(0===Object.keys(Ee).length)return e.jsx(Vt,{description:T("resources:repositories.noRepositories")});const t={machine:"repository",bridge:"bridge",team:"team",region:"region",repository:"repository",status:"status",grand:"grand"},a={team:"var(--color-success)",bridge:"var(--color-primary)",region:"var(--color-info)",repository:"var(--color-secondary)",status:"var(--color-warning)",grand:"var(--color-secondary)"},i={bridge:e.jsx(b,{}),team:e.jsx(w,{}),region:e.jsx(C,{}),repository:e.jsx(S,{}),status:e.jsx(U,{}),grand:e.jsx(Ce,{})};return e.jsx(Ft,{children:Object.entries(Ee).map(([n,s],r)=>{const o=t[F],c=a[o];return e.jsxs(Pt,{$isAlternate:r%2==0,children:[e.jsxs(Ot,{children:[e.jsx(Lt,{$color:c}),e.jsxs(pe,{size:"small",children:[e.jsxs(zt,{children:["#",r+1]}),e.jsx(Kt,{$variant:o,icon:i[F],children:n}),e.jsxs(Gt,{children:[s.length," ",1===s.length?T("machines:machine"):T("machines:machines")]})]})]}),s.map((t,a)=>e.jsxs(_t,{$isStriped:a%2!=0,onClick:()=>R(`/machines/${t.machineName}/repositories`,{state:{machine:t}}),"data-testid":`grouped-machine-row-${t.machineName}`,children:[e.jsxs(Bt,{children:[e.jsx(Ht,{}),e.jsxs(Qt,{children:[e.jsx(Xt,{children:t.machineName}),e.jsxs(pe,{size:"small",children:[e.jsx(Ut,{$variant:"team",children:t.teamName}),t.bridgeName&&e.jsx(Ut,{$variant:"bridge",children:t.bridgeName}),t.regionName&&e.jsx(Ut,{$variant:"region",children:t.regionName})]})]})]}),e.jsx(be,{title:T("machines:viewRepositories"),children:e.jsx(qt,{type:"primary",icon:e.jsx(I,{}),onClick:e=>{e.stopPropagation(),R(`/machines/${t.machineName}/repositories`,{state:{machine:t}})},children:T("machines:viewRepositories")})})]},t.machineName))]},n)})})})(),e.jsx(De,{open:z.isOpen,onCancel:z.close,entityType:z.entityType,entityIdentifier:z.entityIdentifier,entityName:z.entityName}),G.state.data&&e.jsx(se,{open:G.isOpen,onCancel:G.close,machineName:G.state.data.machineName,teamName:G.state.data.teamName,bridgeName:G.state.data.bridgeName,onQueueItemCreated:u}),_.state.data&&e.jsx(ze,{open:_.isOpen,machine:_.state.data,onCancel:_.close,onSuccess:()=>{_.close(),le()}}),e.jsx(ze,{open:B,machines:ie.filter(e=>O.includes(e.machineName)),onCancel:()=>W(!1),onSuccess:()=>{W(!1),L([]),le()}}),e.jsx(Ge,{open:X,machines:ie.filter(e=>O.includes(e.machineName)),onCancel:()=>q(!1),onSuccess:()=>{q(!1),L([]),le()}}),e.jsx(_e,{open:K,machines:ie.filter(e=>O.includes(e.machineName)),onCancel:()=>Z(!1)}),!h&&e.jsx(Ve,{machine:J,visible:ee,onClose:je})]})},Yt=le.div`
  display: flex;
  height: 100%;
  width: 100%;
  position: relative;
  overflow: hidden;
`,ea=le.div`
  width: ${({$width:e})=>e};
  height: 100%;
  overflow: auto;
  min-width: 300px;
  transition: width 0.3s ease-in-out;
`,ta=le.div`
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
`,aa=t=>{const{type:i,selectedResource:n,onResourceSelect:s,isPanelCollapsed:r=!0,onTogglePanelCollapse:o}=t,c=Fe(),[l,m]=a.useState(c),[d,u]=a.useState(!1),[h,p]=a.useState(!1);a.useEffect(()=>{m(c)},[c]),a.useEffect(()=>{if(!n){u(!1);const e=setTimeout(()=>{p(!1)},250);return()=>clearTimeout(e)}p(!0),requestAnimationFrame(()=>{u(!0)})},[n]);const g=e=>{s(e)},x=()=>{s(null)},y=r?Pe.COLLAPSED_WIDTH:l;if("machine"===i){const a=n?`calc(100% - ${y}px)`:"100%";return e.jsxs(Yt,{"data-testid":"split-resource-view-container",children:[e.jsx(ea,{$width:a,"data-testid":"split-resource-view-left-panel",children:e.jsx(Jt,{...t,onRowClick:g,selectedMachine:n})}),h&&e.jsx(ta,{$visible:d,$rightOffset:y,onClick:x,"data-testid":"split-resource-view-backdrop"}),n&&e.jsx(Oe,{type:"machineName"in n?"machine":"repositoryName"in n?"repository":"container",data:n,visible:!0,onClose:x,splitWidth:l,onSplitWidthChange:m,isCollapsed:r,onToggleCollapse:o,collapsedWidth:Pe.COLLAPSED_WIDTH})]})}return null},ia=()=>{const{t:t}=we(["resources","machines","common"]),[n,r]=$e.useModal(),o=s(),c=i(),l=ue(),{teams:m,selectedTeams:d,setSelectedTeams:u,isLoading:h}=Je(),{modalState:p,currentResource:g,openModal:y,closeModal:f}=Ze("machine"),[b,j]=a.useState(null),[v,N]=a.useState(null),[$,w]=a.useState(null),[C,S]=a.useState(!0),[M,I]=a.useState({}),{state:W,open:Q,close:U}=T(),Z=k(),{data:J=[],refetch:Y}=Se(d.length>0?d:void 0,d.length>0),{data:ee=[]}=Me(d.length>0?d:void 0),{data:te=[]}=X(d.length>0?d:void 0),ie=Ie(),ne=Te(),se=Re(),re=Ae(),oe=Ee(),{executeAction:ce,isExecuting:le}=ae();a.useEffect(()=>{const e=o.state;e?.createRepository&&c("/credentials",{state:e,replace:!0})},[o,c]);const me=e=>{j(e),e&&(N(null),w(null),S(!1))},de=a.useCallback(e=>{et({modal:n,t:t,resourceType:"machine",resourceName:e.machineName,translationNamespace:"machines",onConfirm:()=>re.mutateAsync({teamName:e.teamName,machineName:e.machineName}),onSuccess:()=>Y()})},[re,n,Y,t]),he=a.useCallback(async e=>{try{if("create"===p.mode){const{autoSetup:i,...n}=e;if(await ie.mutateAsync(n),x("success",t("machines:createSuccess")),i)try{await new Promise(e=>setTimeout(e,500));const a=await ce({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,functionName:"setup",params:{datastore_size:"95%",source:"apt-repo",rclone_source:"install-script",docker_source:"docker-repo",install_amd_driver:"auto",install_nvidia_driver:"auto"},priority:3,description:`Auto-setup for machine ${e.machineName}`,addedVia:"machine-creation-auto-setup",machineVault:e.machineVault||"{}"});a.success&&(a.taskId?(x("info",t("machines:setupQueued")),Q(a.taskId,e.machineName)):a.isQueued&&x("info",t("machines:setupQueuedForSubmission")))}catch(a){x("warning",t("machines:machineCreatedButSetupFailed"))}f(),Y()}else if(g){const t=g.machineName,a=e.machineName;a&&a!==t&&await ne.mutateAsync({teamName:g.teamName,currentMachineName:t,newMachineName:a}),e.bridgeName&&e.bridgeName!==g.bridgeName&&await se.mutateAsync({teamName:g.teamName,machineName:a||t,newBridgeName:e.bridgeName});const i=e.machineVault;i&&i!==g.vaultContent&&await oe.mutateAsync({teamName:g.teamName,machineName:a||t,machineVault:i,vaultVersion:g.vaultVersion+1}),f(),Y()}}catch(a){}},[f,ie,g,ce,Q,Y,t,p.mode,se,ne,oe]),pe=a.useCallback(async(e,t)=>{if(g)try{await oe.mutateAsync({teamName:g.teamName,machineName:g.machineName,machineVault:e,vaultVersion:t}),f(),Y()}catch(a){}},[f,g,Y,oe]),ge=a.useCallback(async e=>{if(g)try{const a=g.machineName,i=g.bridgeName,n=m.find(e=>e.teamName===g.teamName),s={teamName:g.teamName,machineName:a,bridgeName:i,functionName:e.function.name,params:e.params,priority:e.priority,description:e.description,addedVia:"machine-table",teamVault:n?.vaultContent||"{}",machineVault:g.vaultContent||"{}"};if(e.params.repo){const t=ee.find(t=>t.repositoryGuid===e.params.repo);s.repositoryGuid=t?.repositoryGuid||e.params.repo,s.repositoryVault=t?.vaultContent||"{}"}else s.repositoryVault="{}";if("pull"===e.function.name){if("machine"===e.params.sourceType&&e.params.from){const t=J.find(t=>t.machineName===e.params.from);t?.vaultContent&&(s.sourceMachineVault=t.vaultContent)}if("storage"===e.params.sourceType&&e.params.from){const t=te.find(t=>t.storageName===e.params.from);t?.vaultContent&&(s.sourceStorageVault=t.vaultContent)}}const r=await ce(s);f(),r.success?r.taskId?(x("success",t("machines:queueItemCreated")),Q(r.taskId,a)):r.isQueued&&x("info",t("resources:messages.highestPriorityQueued",{resourceType:"machine"})):x("error",r.error||t("resources:errors.failedToCreateQueueItem"))}catch(a){x("error",t("resources:errors.failedToCreateQueueItem"))}},[f,g,ce,J,Q,ee,te,t,m]),xe=ie.isPending||ne.isPending||se.isPending||le,ye=oe.isPending;return e.jsxs(e.Fragment,{children:[e.jsx(R,{children:e.jsxs(A,{children:[e.jsx(E,{level:3,children:t("machines:heading",{defaultValue:"Machines"})}),e.jsxs(D,{children:[e.jsx(V,{children:e.jsxs(F,{children:[e.jsx(P,{children:e.jsx(O,{children:e.jsx(Ye,{"data-testid":"machines-team-selector",teams:m,selectedTeams:d,onChange:u,loading:h,placeholder:t("teams.selectTeamToView"),style:{width:"100%"}})})}),d.length>0&&e.jsxs(L,{children:[e.jsx(be,{title:t("machines:createMachine"),children:e.jsx(z,{$variant:"primary",icon:e.jsx(G,{}),"data-testid":"machines-create-machine-button",onClick:()=>y("create"),"aria-label":t("machines:createMachine")})}),e.jsx(be,{title:t("machines:connectivityTest"),children:e.jsx(z,{icon:e.jsx(H,{}),"data-testid":"machines-connectivity-test-button",onClick:()=>Z.open(),disabled:0===J.length,"aria-label":t("machines:connectivityTest")})}),e.jsx(be,{title:t("common:actions.refresh"),children:e.jsx(z,{icon:e.jsx(B,{}),"data-testid":"machines-refresh-button",onClick:()=>{Y(),I(e=>({...e,_global:Date.now()}))},"aria-label":t("common:actions.refresh")})})]})]})}),e.jsx(_,{children:0===d.length?e.jsx(je,{image:je.PRESENTED_IMAGE_SIMPLE,description:t("teams.selectTeamPrompt"),style:{padding:`${l.spacing.LG}px 0`}}):e.jsx(aa,{type:"machine",teamFilter:d,showFilters:!0,showActions:!0,onCreateMachine:()=>y("create"),onEditMachine:e=>y("edit",e),onVaultMachine:e=>y("vault",e),onFunctionsMachine:(e,t)=>{y("create",e,t),I(t=>({...t,[e.machineName]:Date.now()}))},onDeleteMachine:de,enabled:d.length>0,refreshKeys:M,onQueueItemCreated:(e,t)=>{Q(e,t)},selectedResource:b||v||$,onResourceSelect:e=>{e&&"machineName"in e?me(e):e&&"repositoryName"in e?(me(null),N(e),w(null),S(!1)):e&&"id"in e&&"state"in e?(me(null),N(null),w(e),S(!1)):(me(null),N(null),w(null))},isPanelCollapsed:C,onTogglePanelCollapse:()=>{S(e=>!e)}})})]})]})}),e.jsx(q,{"data-testid":"machines-machine-modal",open:p.open,onCancel:f,resourceType:"machine",mode:p.mode,existingData:p.data||g,teamFilter:d.length>0?d:void 0,preselectedFunction:p.preselectedFunction,onSubmit:he,onUpdateVault:"edit"===p.mode?pe:void 0,onFunctionSubmit:ge,isSubmitting:xe,isUpdatingVault:ye,functionCategories:["machine","backup"],hiddenParams:[],defaultParams:{}}),e.jsx(K,{"data-testid":"machines-queue-trace-modal",taskId:W.taskId,open:W.open,onCancel:()=>{const e=W.machineName;U(),e&&I(t=>({...t,[e]:Date.now()})),Y()}}),e.jsx(Ct,{"data-testid":"machines-connectivity-test-modal",open:Z.isOpen,onClose:Z.close,machines:J,teamFilter:d}),r]})};export{ia as default};
