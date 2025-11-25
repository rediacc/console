import{j as e,u as t}from"./chunk-DXoLy3RZ.js";import{r as a,j as i,R as n,u as s}from"./chunk-ZRs5Vi2W.js";import{B as r,M as o,e as c,f as l,g as m,h as d,i as u,j as h,b as p,C as g,s as x,k as y,D as f,H as b,l as j,m as v,n as k,o as N,T as $,G as w,I as C,d as S,R as M,p as I,P as T,q as R,t as A,v as E,w as D,x as V,y as F,z as P,A as O,F as z,J as L,K as G}from"../index-BL9oc91X.js";import{R as _}from"./chunk-BOBTNXYy.js";import{u as B,W}from"./chunk-DNIhkNGD.js";import{u as H,a as Q,U as X}from"./chunk-BY4kY47k.js";import{D as q,Q as U}from"./chunk-CNhb2Jdx.js";import{S as K}from"./chunk-gDr8sflD.js";import{C as Z}from"./chunk-yorGyJOQ.js";import{u as J}from"./chunk-D8Tk7nNA.js";import{u as Y,A as ee,a as te}from"./chunk-DdIWLSM3.js";import{u as ae}from"./chunk-BN0o6Dk5.js";import{w as ie,R as ne}from"./chunk-DoZGTYOJ.js";import{c as se,a as re,b as oe}from"./chunk-Bfi5ED4P.js";import{d as ce,m as le,a as me,n as de}from"./chunk-m5fYU7UF.js";import{T as ue,S as he,c as pe,P as ge,A as xe,d as ye,o as fe,E as be,C as je,B as ve,F as ke,M as Ne}from"./chunk-2wWKRBEk.js";import{u as $e}from"./chunk-BYo3s0jF.js";import{C as we}from"./chunk-BYB5CQV8.js";import{B as Ce}from"./chunk-h6RFt10x.js";import{u as Se,a as Me,b as Ie,c as Te,d as Re,e as Ae,f as Ee}from"./chunk-CrHXuqsJ.js";import{A as De}from"./chunk-BOJNGWU3.js";import{M as Ve,u as Fe,D as Pe,U as Oe}from"./chunk-_qoww5Lh.js";import{M as ze,A as Le,R as Ge,V as _e}from"./chunk-eBy9nc8w.js";import"./chunk-DZV5yM2-.js";import{g as Be}from"./chunk-DYR6ZHxn.js";import{c as We,a as He}from"./chunk-CafmTZyt.js";import{D as Qe,E as Xe,L as qe}from"./chunk-DDg0Spjq.js";import{E as Ue}from"./chunk-CUh1jUyo.js";import{F as Ke}from"./chunk-B8Pnrez7.js";import{u as Ze}from"./chunk-BNvdSKJ_.js";import{u as Je,T as Ye}from"./chunk-DMc643ui.js";import{c as et}from"./chunk-BuHtHQ7Z.js";import"./chunk-_auT2Wjb.js";import"./chunk-CALlPgAP.js";import"./chunk-B2-hwM9e.js";import"./chunk-By0bf0gv.js";import"./chunk-c8SiAiED.js";import"./chunk--pNmZQLv.js";import"./chunk-DElvqJ3v.js";import"./chunk-ChKcEqht.js";import"./chunk-D1ULqfEc.js";import"./chunk-CmjwjsRG.js";import"./chunk-DhpoEw86.js";import"./chunk-cKYU955c.js";import"./chunk-BJ3vZdQ9.js";import"./chunk-DmEfCd0s.js";import"./chunk-7skYLAuF.js";import"./chunk-CDKvQETH.js";import"./chunk-_ZJBsyZa.js";import"./forkTokenService.ts-B6ApTP_P.js";import"./chunk-CmUZ4osn.js";function tt(e){const{buildQueueVault:t}=B();Y();const i=J(),{data:n}=ae(),s=a.useCallback(async e=>{try{const a=function(e,t){if(e.teamVault&&"{}"!==e.teamVault)return e.teamVault;const a=t?.find(t=>t.teamName===e.teamName);return a?.vaultContent||"{}"}(e,n),s=await async function(e,t,a){const i=4,n="Ping connectivity test",s="ping-service",r="{}";return a({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,functionName:"ping",params:{},priority:e.priority||i,description:e.description||n,addedVia:e.addedVia||s,machineVault:e.machineVault||r,teamVault:t,repositoryVault:e.repositoryVault||r})}(e,a,t),r=await async function(e,t,a){const i=4;return a.mutateAsync({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,queueVault:t,priority:e.priority||i})}(e,s,i);return{taskId:r?.taskId,success:!!r?.taskId||!!r?.isQueued}}catch(a){return{success:!1,error:a.message||"Failed to execute ping function"}}},[t,i,n]),r=a.useCallback(async(e,t)=>s({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,priority:t?.priority,description:t?.description,addedVia:t?.addedVia,machineVault:e.vaultContent||"{}"}),[s]),o=a.useCallback(async(e,t)=>{const a=await s(e);if(!a.success||!a.taskId)return a;const i=await ie(a.taskId,t);return{...a,completionResult:i,success:i.success,error:i.success?void 0:i.message}},[s]),c=a.useCallback(async(e,t)=>o({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,priority:t?.priority,description:t?.description,addedVia:t?.addedVia,machineVault:e.vaultContent||"{}"},t?.timeout),[o]);return{executePing:s,executePingForMachine:r,executePingAndWait:o,executePingForMachineAndWait:c,waitForQueueItemCompletion:ie,isLoading:i.isPending}}const{Text:at}=ue,it=le`
  0% {
    opacity: 0.65;
  }
  50% {
    opacity: 1;
  }
  100% {
    opacity: 0.65;
  }
`,nt=ce(r)`
  .ant-modal-body {
    padding: ${({theme:e})=>e.spacing.XL}px;
  }
`,st=ce(o)`
  width: 100%;
`,rt=ce(c)``,ot=ce(he)`
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
`,ct=ce(l)``,lt=ce(m)`
  && {
    min-width: ${({theme:e})=>2*e.spacing.XXL}px;
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,mt=ce(pe)`
  && {
    min-width: ${({theme:e})=>e.dimensions.CONTROL_HEIGHT}px;
    min-height: ${({theme:e})=>e.dimensions.CONTROL_HEIGHT}px;
    border-radius: ${({theme:e})=>e.borderRadius.LG}px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,dt=ce.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XS}px;
`,ut=ce(ge)`
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
`,ht=ce(at)`
  && {
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    color: ${({theme:e})=>e.colors.textSecondary};
  }
`,pt=ce(xe)`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.LG}px;
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,gt=ce.div`
  padding: ${({theme:e})=>e.spacing.MD}px;
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
  background-color: ${({theme:e})=>e.colors.bgSecondary};
`,xt=ce.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({theme:e})=>e.spacing.XL}px;
`,yt=ce.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XS}px;
`,ft=ce(at)`
  && {
    color: ${({theme:e})=>e.colors.textSecondary};
  }
`,bt=ce(at)`
  && {
    color: ${({theme:e,$variant:t})=>"success"===t?e.colors.success:"error"===t?e.colors.error:e.colors.textPrimary};
    font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
  }
`,jt=ce(d)`
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
`,vt=ce.div`
  display: inline-flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,kt=ce(at)`
  && {
    font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
  }
`,Nt=ce.span`
  display: inline-flex;
  align-items: center;
  color: ${({theme:e,$variant:t})=>{switch(t){case"success":return e.colors.success;case"failed":return e.colors.error;case"testing":return e.colors.primary;default:return e.colors.textSecondary}}};

  .anticon {
    font-size: ${({theme:e})=>e.fontSize.LG}px;
  }
`,$t=ce(ye)`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.MD}px;
    border-color: ${({theme:e})=>e.colors.borderSecondary};
    color: ${({theme:e})=>e.colors.textPrimary};
    background-color: ${({theme:e})=>e.colors.bgSecondary};
  }
`;ce(u)`
  && {
    text-transform: capitalize;
  }
`;const wt=ce(at)`
  && {
    color: ${({theme:e,$isError:t})=>t?e.colors.error:e.colors.textPrimary};
  }
`,Ct=({open:t,onClose:i,machines:n})=>{const{t:s}=$e(["machines","common"]),[r,o]=a.useState([]),[c,l]=a.useState(!1),[m,d]=a.useState(0),[u,y]=a.useState(-1),{executePingForMachine:f,waitForQueueItemCompletion:b}=tt();a.useEffect(()=>{if(t&&n.length>0){const e=n.map(e=>({machineName:e.machineName,teamName:e.teamName,bridgeName:e.bridgeName,status:"pending"}));o(e),d(0),y(-1)}},[t,n]);const j=e=>e.success?s("machines:connectionSuccessful"):"TIMEOUT"===e.status?s("machines:testTimeout"):e.message||s("machines:connectionFailed"),v=async(e,t)=>{const a=Date.now();o(e=>e.map((e,a)=>a===t?{...e,status:"testing",timestamp:(new Date).toISOString()}:e));try{const i=await f(e,{priority:4,description:"Connectivity test",addedVia:"connectivity-test"});if(!i.success||!i.taskId)throw new Error(i.error||"Failed to create test task");{o(e=>e.map((e,a)=>a===t?{...e,taskId:i.taskId}:e));const e=await b(i.taskId),n=Date.now()-a;o(a=>a.map((a,i)=>i===t?{...a,status:e.success?"success":"failed",message:j(e),duration:n}:a))}}catch(i){const e=i instanceof Error?i.message:"Failed to create test task",n=Date.now()-a;o(a=>a.map((a,i)=>i===t?{...a,status:"failed",message:e,duration:n}:a))}},k=se({title:s("machines:team"),dataIndex:"teamName",key:"teamName",renderWrapper:t=>e.jsx($t,{children:t})}),N=se({title:s("machines:bridge"),dataIndex:"bridgeName",key:"bridgeName",renderWrapper:t=>e.jsx($t,{children:t})}),$=re({title:s("machines:status"),dataIndex:"status",key:"status",width:140,statusMap:{pending:{color:"default",label:s("machines:pending"),icon:e.jsx(g,{})},testing:{color:"blue",label:s("machines:testing"),icon:e.jsx(K,{spin:!0})},success:{color:"success",label:s("machines:connected"),icon:e.jsx(p,{})},failed:{color:"error",label:s("machines:failed"),icon:e.jsx(Z,{})}}}),w=se({title:s("machines:message"),dataIndex:"message",key:"message",ellipsis:!0,renderText:e=>e||"-"}),C=[{title:s("machines:machineName"),dataIndex:"machineName",key:"machineName",render:(t,a)=>e.jsxs(vt,{"data-testid":`connectivity-machine-${t}`,children:[e.jsx(Nt,{$variant:a.status,children:(()=>{switch(a.status){case"testing":return e.jsx(K,{spin:!0,"data-testid":`connectivity-status-icon-testing-${t}`});case"success":return e.jsx(p,{"data-testid":`connectivity-status-icon-success-${t}`});case"failed":return e.jsx(Z,{"data-testid":`connectivity-status-icon-failed-${t}`});default:return e.jsx(g,{"data-testid":`connectivity-status-icon-pending-${t}`})}})()}),e.jsx(kt,{children:t})]})},k,N,{...$,render:(t,a,i)=>e.jsx("span",{"data-testid":`connectivity-status-tag-${a.machineName}-${t}`,children:$.render?.(t,a,i)})},{title:s("machines:responseTime"),dataIndex:"duration",key:"duration",width:120,render:e=>e?e<1e3?`${e}ms`:`${(e/1e3).toFixed(1)}s`:"-"},{...w,render:(t,a,i)=>{if(!t)return w.render?.(t,a,i);const n=w.render?.(t,a,i);return e.jsx(wt,{$isError:"failed"===a.status,children:n})}}];return e.jsx(nt,{"data-testid":"connectivity-modal",title:e.jsxs(ot,{children:[e.jsx(W,{}),s("machines:connectivityTest")]}),open:t,onCancel:i,className:h.ExtraLarge,destroyOnHidden:!0,footer:e.jsxs(ct,{children:[e.jsx(lt,{type:"primary",icon:e.jsx(K,{}),onClick:async()=>{l(!0);for(let a=0;a<n.length;a++)y(a),d(Math.round(a/n.length*100)),await v(n[a],a);d(100),l(!1),y(-1);const e=r.filter(e=>"success"===e.status).length,t=r.filter(e=>"failed"===e.status).length;0===t?x("success",s("machines:allMachinesConnected",{count:e})):x("warning",s("machines:machinesConnectedWithFailures",{successCount:e,failedCount:t}))},disabled:c||0===n.length,loading:c,"data-testid":"connectivity-run-test-button",children:s(c?"machines:testing":"machines:runTest")}),e.jsx(fe,{title:"Close",children:e.jsx(mt,{icon:e.jsx(Z,{}),onClick:i,"data-testid":"connectivity-close-button","aria-label":"Close"})})]}),children:e.jsx(st,{children:e.jsxs(rt,{children:[c&&e.jsxs(dt,{"data-testid":"connectivity-progress-container",children:[e.jsx(ut,{percent:m,status:"active","data-testid":"connectivity-progress-bar"}),u>=0&&u<n.length&&e.jsx(ht,{"data-testid":"connectivity-progress-text",children:s("machines:testingMachine",{machineName:n[u].machineName})})]}),e.jsx(pt,{message:s("machines:connectivityTestDescription"),type:"info",showIcon:!0,icon:e.jsx(W,{}),"data-testid":"connectivity-info-alert"}),e.jsx(jt,{columns:C,dataSource:r,rowKey:"machineName",pagination:!1,scroll:{y:400},loading:0===n.length,rowClassName:e=>`status-${e.status}`,"data-testid":"connectivity-results-table"}),!c&&r.some(e=>"pending"!==e.status)&&e.jsx(gt,{"data-testid":"connectivity-summary-statistics",children:e.jsxs(xt,{children:[e.jsxs(yt,{"data-testid":"connectivity-total-machines",children:[e.jsxs(ft,{children:[s("machines:totalMachines"),":"]}),e.jsx(bt,{children:n.length})]}),e.jsxs(yt,{"data-testid":"connectivity-connected-count",children:[e.jsxs(ft,{children:[s("machines:connected"),":"]}),e.jsx(bt,{$variant:"success",children:r.filter(e=>"success"===e.status).length})]}),e.jsxs(yt,{"data-testid":"connectivity-failed-count",children:[e.jsxs(ft,{children:[s("machines:failed"),":"]}),e.jsx(bt,{$variant:"error",children:r.filter(e=>"failed"===e.status).length})]}),e.jsxs(yt,{"data-testid":"connectivity-average-response",children:[e.jsxs(ft,{children:[s("machines:averageResponse"),":"]}),e.jsx(bt,{children:(()=>{const e=r.filter(e=>"success"===e.status&&e.duration);if(0===e.length)return"-";const t=e.reduce((e,t)=>e+(t.duration||0),0)/e.length;return t<1e3?`${Math.round(t)}ms`:`${(t/1e3).toFixed(1)}s`})()})]})]})})]})})})},St={team:{background:"var(--color-success)",color:"var(--color-text-inverse)"},bridge:{background:"var(--color-primary)",color:"var(--color-text-inverse)"},region:{background:"var(--color-info)",color:"var(--color-text-inverse)"},repository:{background:"var(--color-secondary)",color:"var(--color-text-inverse)"},status:{background:"var(--color-warning)",color:"var(--color-text-inverse)"},grand:{background:"var(--color-secondary)",color:"var(--color-text-inverse)"}},Mt=ce.div`
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
`,It=ce.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
`,Tt=ce.div`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
  padding: ${({theme:e})=>e.spacing.SM}px ${({theme:e})=>e.spacing.MD}px;
  background-color: var(--color-bg-secondary);
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border: 1px solid var(--color-border-secondary);
  gap: ${({theme:e})=>e.spacing.MD}px;
`,Rt=ce.span`
  font-weight: 600;
  color: var(--color-text-primary);
`,At=ce.div`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
`,Et=ce(pe)`
  && {
    min-width: 42px;
    height: ${y.DIMENSIONS.CONTROL_HEIGHT_SM}px;
    border-radius: ${({theme:e})=>e.borderRadius.SM}px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
`,Dt=ce.span`
  width: 1px;
  height: 24px;
  background-color: var(--color-border-secondary);
  margin: 0 ${({theme:e})=>e.spacing.SM}px;
`,Vt=ce(be).attrs({image:be.PRESENTED_IMAGE_SIMPLE})`
  margin-top: ${({theme:e})=>e.spacing.XL}px;
`,Ft=ce.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XL}px;
`,Pt=ce(je)`
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
`,Ot=ce.div`
  display: flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
  padding: ${({theme:e})=>e.spacing.XS}px 0;
`,zt=ce.div`
  width: 4px;
  height: ${y.DIMENSIONS.ICON_XL}px;
  border-radius: ${({theme:e})=>e.borderRadius.SM}px;
  background-color: ${({$color:e})=>e||"var(--color-text-secondary)"};
`,Lt=ce.span`
  font-size: 18px;
  font-weight: 700;
  color: var(--color-text-primary);
`,Gt=ce.span`
  font-size: 14px;
  color: var(--color-text-secondary);
`,_t=ce.div`
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
`,Bt=ce.div`
  display: flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.LG}px;
`,Wt=ce(f)`
  font-size: ${y.DIMENSIONS.ICON_MD}px;
  color: var(--color-primary);
`,Ht=ce(Wt)`
  font-size: ${y.DIMENSIONS.ICON_LG}px;
`,Qt=ce.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XS}px;
`,Xt=ce.span`
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
`,qt=ce(pe)`
  && {
    /* Maintain compact pill styling to mirror historical control surface */
    height: ${y.DIMENSIONS.CONTROL_HEIGHT_SM}px;
    border-radius: ${({theme:e})=>e.borderRadius.SM}px;
    display: inline-flex;
    align-items: center;
    gap: ${({theme:e})=>e.spacing.XS}px;
  }
`;ce.span`
  font-size: 18px;
  color: ${({$status:e})=>{switch(e){case"online":return"var(--color-success)";case"offline":return"var(--color-text-tertiary)";default:return"var(--color-text-quaternary)"}}};
  display: inline-flex;
  align-items: center;
  justify-content: center;
`;const Ut=ce(ye)`
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
`,Kt=ce(Ut)`
  && {
    font-size: 16px;
    padding: 4px ${({theme:e})=>e.spacing.MD}px;
  }
`,Zt=ce(ve)`
  && .ant-badge-count {
    background-color: ${({$isPositive:e})=>e?"var(--color-success)":"var(--color-border-secondary)"};
    color: ${({$isPositive:e})=>e?"var(--color-text-inverse)":"var(--color-text-secondary)"};
  }
`,Jt=({teamFilter:s,showActions:r=!0,className:o="",onEditMachine:c,onFunctionsMachine:l,onDeleteMachine:m,enabled:d=!0,onQueueItemCreated:u,onRowClick:h,selectedMachine:g})=>{const{t:I}=$e(["machines","common","functions","resources"]),T=i(),R=t(e=>e.ui.uiMode),A="expert"===R,{executePingForMachineAndWait:E}=tt(),D=a.useRef(null),[V,F]=a.useState("machine"),[P,O]=a.useState([]),z=v(),L=k(),G=k(),[_,B]=a.useState(!1),[Q,X]=a.useState(!1),[U,K]=a.useState(!1),[Z,J]=a.useState(null),[Y,te]=a.useState(!1);n.useEffect(()=>{"simple"===R&&"machine"!==V&&F("machine")},[R,V]);const{data:ae=[],isLoading:ie,refetch:ce}=Se(s,d),{data:le=[]}=Me(s),de=((e,t={})=>{const{rowHeight:i=54,headerHeight:n=55,paginationHeight:s=64,containerOffset:r=32,minRows:o=5,maxRows:c=100}=t,[l,m]=a.useState(10),d=a.useRef(null),u=a.useCallback(()=>{if(!e.current)return;const t=e.current.offsetHeight-n-s-r,a=Math.floor(t/i),l=Math.max(o,Math.min(c,a));m(l)},[e,i,n,s,r,o,c]),h=a.useRef(null);return a.useEffect(()=>(h.current=me.debounce(u,300),()=>{h.current?.cancel()}),[u]),a.useEffect(()=>(u(),e.current&&window.ResizeObserver&&(d.current=new ResizeObserver(()=>{h.current?.()}),d.current.observe(e.current)),()=>{d.current&&d.current.disconnect(),h.current?.cancel()}),[u,e]),l})(D,{containerOffset:170,minRows:5,maxRows:50}),ue=ae,ge=e=>Be(e,le.map(e=>({repositoryGuid:e.repositoryGuid,repositoryName:e.repositoryName,grandGuid:e.grandGuid}))),xe=a.useCallback(e=>{m&&m(e)},[m]),ye=a.useCallback(e=>{h?h(e):(J(e),te(!0))},[h]),be=a.useCallback(()=>{te(!1),J(null)},[]),{getFunctionsByCategory:je}=H(),ve=a.useMemo(()=>je("machine").filter(e=>e&&!1!==e.showInMenu&&"mount"!==e.name&&"pull"!==e.name),[je]),Ne=A&&N.isEnabled("assignToCluster"),Ie=a.useCallback(e=>{e.open&&e.machine?G.open(e.machine):G.close()},[G]),Te=a.useCallback(e=>{e.open&&e.entityType&&e.entityIdentifier?z.open({entityType:e.entityType,entityIdentifier:e.entityIdentifier,entityName:e.entityName}):z.close()},[z]),Re=n.useMemo(()=>(({t:t,isExpertMode:a,uiMode:i,showActions:n,hasSplitView:s,canAssignToCluster:r,onEditMachine:o,onFunctionsMachine:c,handleDelete:l,handleRowClick:m,executePingForMachineAndWait:d,setAssignClusterModal:u,setAuditTraceModal:h,machineFunctions:g})=>{const f=[],v=se({title:t("machines:machineName"),dataIndex:"machineName",key:"machineName",sorter:We("machineName"),renderWrapper:t=>e.jsxs(he,{children:[e.jsx(Wt,{}),e.jsx("strong",{children:t})]})});return f.push(re({title:t("machines:status"),dataIndex:"vaultStatusTime",key:"status",statusMap:{online:{icon:e.jsx(p,{}),label:t("machines:connected"),color:"success"},offline:{icon:e.jsx(Qe,{}),label:t("machines:connectionFailed"),color:"error"},unknown:{icon:e.jsx(Qe,{}),label:t("machines:statusUnknown"),color:"default"}},sorter:He(e=>{if(!e.vaultStatusTime)return 1/0;const t=new Date(e.vaultStatusTime+"Z");return((new Date).getTime()-t.getTime())/6e4<=3?0:1}),renderValue:(e,t)=>{if(!t.vaultStatusTime)return"unknown";const a=new Date(t.vaultStatusTime+"Z");return((new Date).getTime()-a.getTime())/6e4<=3?"online":"offline"}}),v),s||f.push(se({title:t("machines:team"),dataIndex:"teamName",key:"teamName",width:150,sorter:We("teamName"),renderWrapper:t=>e.jsx(Ut,{$variant:"team",children:t})})),s||(a?f.push(se({title:t("machines:region"),dataIndex:"regionName",key:"regionName",width:150,sorter:We("regionName"),renderText:e=>e||"-",renderWrapper:(t,a)=>"-"===a?e.jsx("span",{children:"-"}):e.jsx(Ut,{$variant:"region",children:t})}),se({title:t("machines:bridge"),dataIndex:"bridgeName",key:"bridgeName",width:150,sorter:We("bridgeName"),renderWrapper:t=>e.jsx(Ut,{$variant:"bridge",children:t})})):"simple"!==i&&f.push(se({title:t("bridges.bridge"),dataIndex:"bridgeName",key:"bridgeName",width:150,sorter:We("bridgeName"),renderWrapper:t=>e.jsx(Ut,{$variant:"bridge",children:t})}))),!s&&r&&f.push({title:t("machines:assignmentStatus.title"),key:"assignmentStatus",width:180,ellipsis:!0,render:(t,a)=>e.jsx(ze,{machine:a})}),s||f.push({title:t("machines:queueItems"),dataIndex:"queueCount",key:"queueCount",width:100,align:"center",sorter:We("queueCount"),render:t=>e.jsx(Zt,{$isPositive:t>0,count:t,showZero:!0})}),n&&f.push(oe({title:t("common:table.actions"),width:y.DIMENSIONS.CARD_WIDTH,renderActions:a=>e.jsx(ee,{buttons:[{type:"view",icon:e.jsx(Xe,{}),tooltip:"common:viewDetails",onClick:()=>m(a),variant:"default",testIdSuffix:"view-details"},{type:"edit",icon:e.jsx(Ue,{}),tooltip:"common:actions.edit",onClick:()=>o?.(a)},{type:"remote",icon:e.jsx(Ke,{}),tooltip:"machines:remote",dropdownItems:[{key:"functions",label:t("machines:runAction"),icon:e.jsx(Ke,{}),children:[...g.filter(e=>!1!==e?.showInMenu).map(t=>({key:`function-${t?.name||"unknown"}`,label:e.jsx("span",{title:t?.description||"",children:t?.name||"Unknown"}),onClick:()=>c?.(a,t?.name)})),{type:"divider"},{key:"advanced",label:t("machines:advanced"),icon:e.jsx(Ke,{}),onClick:()=>c?.(a)}]},{key:"test",label:t("machines:connectivityTest"),icon:e.jsx(W,{}),onClick:async()=>{x("info",t("machines:testingConnection"));const e=await d(a,{priority:4,description:"Connectivity test",addedVia:"machine-table",timeout:15e3});e.success?x("success",t("machines:connectionSuccessful")):x("error",e.error||t("machines:connectionFailed"))}},...r?[{key:"assignCluster",label:a.distributedStorageClusterName?t("machines:changeClusterAssignment"):t("machines:assignToCluster"),icon:e.jsx(we,{}),onClick:()=>u({open:!0,machine:a})}]:[]]},{type:"trace",icon:e.jsx(b,{}),tooltip:"machines:trace",onClick:()=>h({open:!0,entityType:"Machine",entityIdentifier:a.machineName,entityName:a.machineName})},{type:"delete",icon:e.jsx(j,{}),tooltip:"common:actions.delete",onClick:()=>l(a),danger:!0},{type:"custom",render:t=>e.jsx(qe,{machine:t.machineName,teamName:t.teamName})}],record:a,idField:"machineName",testIdPrefix:"machine",t:t})})),f})({t:I,isExpertMode:A,uiMode:R,showActions:r,hasSplitView:Boolean(h),canAssignToCluster:Ne,onEditMachine:c,onFunctionsMachine:l,handleDelete:xe,handleRowClick:ye,executePingForMachineAndWait:E,setAssignClusterModal:Ie,setAuditTraceModal:Te,machineFunctions:ve}),[I,A,R,r,h,Ne,c,l,xe,ye,E,Ie,Te,ve]),Ae=Ne?{selectedRowKeys:P,onChange:e=>{O(e)},getCheckboxProps:e=>({disabled:!1,"data-testid":`machine-checkbox-${e.machineName}`})}:void 0,Ee=a.useMemo(()=>{const e={};return"machine"===V||ue.forEach(t=>{let a="";if("bridge"===V)a=t.bridgeName;else if("team"===V)a=t.teamName;else if("region"===V)a=t.regionName||"Unknown";else{if("repository"===V){const a=ge(t);if(0===a.length)return;return void a.forEach(a=>{const i=a.name;e[i]||(e[i]=[]),e[i].find(e=>e.machineName===t.machineName)||e[i].push(t)})}if("status"===V){const e=ge(t);if(0===e.length)a="No Repositories";else{const t=e.some(e=>!e.accessible),i=e.some(e=>e.mounted&&e.docker_running),n=e.some(e=>e.mounted&&!e.docker_running),s=e.some(e=>!e.mounted);a=t?"Inaccessible":i?"Active (Running)":n?"Ready (Stopped)":s?"Not Mounted":"Unknown Status"}}else if("grand"===V){const a=ge(t);if(0===a.length)return;return void a.forEach(a=>{let i="No Grand Repository";if(a.grandGuid){const e=le.find(e=>e.repositoryGuid===a.grandGuid);e&&(i=e.repositoryName)}e[i]||(e[i]=[]),e[i].find(e=>e.machineName===t.machineName)||e[i].push(t)})}}a&&(e[a]||(e[a]=[]),e[a].push(t))}),e},[ue,V,le,ge]);return e.jsxs(Mt,{className:o,children:["simple"===R?null:e.jsx(At,{children:e.jsxs(he,{wrap:!0,size:"small",children:[e.jsx(fe,{title:I("machines:machine"),children:e.jsx(Et,{type:"machine"===V?"primary":"default",icon:e.jsx(f,{}),onClick:()=>F("machine"),"data-testid":"machine-view-toggle-machine","aria-label":I("machines:machine")})}),e.jsx(Dt,{}),e.jsx(fe,{title:I("machines:groupByBridge"),children:e.jsx(Et,{type:"bridge"===V?"primary":"default",icon:e.jsx(we,{}),onClick:()=>F("bridge"),"data-testid":"machine-view-toggle-bridge","aria-label":I("machines:groupByBridge")})}),e.jsx(fe,{title:I("machines:groupByTeam"),children:e.jsx(Et,{type:"team"===V?"primary":"default",icon:e.jsx($,{}),onClick:()=>F("team"),"data-testid":"machine-view-toggle-team","aria-label":I("machines:groupByTeam")})}),A&&e.jsx(fe,{title:I("machines:groupByRegion"),children:e.jsx(Et,{type:"region"===V?"primary":"default",icon:e.jsx(w,{}),onClick:()=>F("region"),"data-testid":"machine-view-toggle-region","aria-label":I("machines:groupByRegion")})}),e.jsx(fe,{title:I("machines:groupByRepository"),children:e.jsx(Et,{type:"repository"===V?"primary":"default",icon:e.jsx(C,{}),onClick:()=>F("repository"),"data-testid":"machine-view-toggle-repository","aria-label":I("machines:groupByRepository")})}),e.jsx(fe,{title:I("machines:groupByStatus"),children:e.jsx(Et,{type:"status"===V?"primary":"default",icon:e.jsx(q,{}),onClick:()=>F("status"),"data-testid":"machine-view-toggle-status","aria-label":I("machines:groupByStatus")})}),e.jsx(fe,{title:I("machines:groupByGrand"),children:e.jsx(Et,{type:"grand"===V?"primary":"default",icon:e.jsx(Ce,{}),onClick:()=>F("grand"),"data-testid":"machine-view-toggle-grand","aria-label":I("machines:groupByGrand")})})]})}),Ne&&0!==P.length?e.jsxs(Tt,{children:[e.jsxs(he,{size:"middle",children:[e.jsx(Rt,{children:I("machines:bulkActions.selected",{count:P.length})}),e.jsx(fe,{title:I("common:actions.clearSelection"),children:e.jsx(pe,{size:"small",onClick:()=>O([]),"data-testid":"machine-bulk-clear-selection","aria-label":I("common:actions.clearSelection")})})]}),e.jsxs(he,{size:"middle",children:[e.jsx(fe,{title:I("machines:bulkActions.assignToCluster"),children:e.jsx(pe,{type:"primary",icon:e.jsx(we,{}),onClick:()=>B(!0),"data-testid":"machine-bulk-assign-cluster","aria-label":I("machines:bulkActions.assignToCluster")})}),e.jsx(fe,{title:I("machines:bulkActions.removeFromCluster"),children:e.jsx(pe,{icon:e.jsx(we,{}),onClick:()=>X(!0),"data-testid":"machine-bulk-remove-cluster","aria-label":I("machines:bulkActions.removeFromCluster")})}),e.jsx(fe,{title:I("machines:bulkActions.viewAssignmentStatus"),children:e.jsx(pe,{icon:e.jsx(S,{}),onClick:()=>K(!0),"data-testid":"machine-bulk-view-status","aria-label":I("machines:bulkActions.viewAssignmentStatus")})})]})]}):null,"machine"===V?e.jsx(It,{ref:D,children:e.jsx(ke,{columns:Re,dataSource:ue,rowKey:"machineName",loading:ie,scroll:{x:"max-content"},rowSelection:Ae,rowClassName:e=>{const t="machine-table-row";return g?.machineName===e.machineName?`${t} machine-table-row--selected`:t},"data-testid":"machine-table",pagination:{pageSize:de,showSizeChanger:!1,showTotal:(e,t)=>I("common:table.showingRecords",{start:t[0],end:t[1],total:e})},onRow:e=>({"data-testid":`machine-row-${e.machineName}`,onClick:t=>{const a=t.target;a.closest("button")||a.closest(".ant-dropdown")||a.closest(".ant-dropdown-menu")||T(`/machines/${e.machineName}/repositories`,{state:{machine:e}})}}),sticky:!0})}):(()=>{if(0===Object.keys(Ee).length)return e.jsx(Vt,{description:I("resources:repositories.noRepositories")});const t={machine:"repository",bridge:"bridge",team:"team",region:"region",repository:"repository",status:"status",grand:"grand"},a={team:"var(--color-success)",bridge:"var(--color-primary)",region:"var(--color-info)",repository:"var(--color-secondary)",status:"var(--color-warning)",grand:"var(--color-secondary)"},i={bridge:e.jsx(we,{}),team:e.jsx($,{}),region:e.jsx(w,{}),repository:e.jsx(C,{}),status:e.jsx(q,{}),grand:e.jsx(Ce,{})};return e.jsx(Ft,{children:Object.entries(Ee).map(([n,s],r)=>{const o=t[V],c=a[o];return e.jsxs(Pt,{$isAlternate:r%2==0,children:[e.jsxs(Ot,{children:[e.jsx(zt,{$color:c}),e.jsxs(he,{size:"small",children:[e.jsxs(Lt,{children:["#",r+1]}),e.jsx(Kt,{$variant:o,icon:i[V],children:n}),e.jsxs(Gt,{children:[s.length," ",1===s.length?I("machines:machine"):I("machines:machines")]})]})]}),s.map((t,a)=>e.jsxs(_t,{$isStriped:a%2!=0,onClick:()=>T(`/machines/${t.machineName}/repositories`,{state:{machine:t}}),"data-testid":`grouped-machine-row-${t.machineName}`,children:[e.jsxs(Bt,{children:[e.jsx(Ht,{}),e.jsxs(Qt,{children:[e.jsx(Xt,{children:t.machineName}),e.jsxs(he,{size:"small",children:[e.jsx(Ut,{$variant:"team",children:t.teamName}),t.bridgeName&&e.jsx(Ut,{$variant:"bridge",children:t.bridgeName}),t.regionName&&e.jsx(Ut,{$variant:"region",children:t.regionName})]})]})]}),e.jsx(fe,{title:I("machines:viewRepositories"),children:e.jsx(qt,{type:"primary",icon:e.jsx(M,{}),onClick:e=>{e.stopPropagation(),T(`/machines/${t.machineName}/repositories`,{state:{machine:t}})},children:I("machines:viewRepositories")})})]},t.machineName))]},n)})})})(),e.jsx(De,{open:z.isOpen,onCancel:z.close,entityType:z.entityType,entityIdentifier:z.entityIdentifier,entityName:z.entityName}),L.state.data&&e.jsx(ne,{open:L.isOpen,onCancel:L.close,machineName:L.state.data.machineName,teamName:L.state.data.teamName,bridgeName:L.state.data.bridgeName,onQueueItemCreated:u}),G.state.data&&e.jsx(Le,{open:G.isOpen,machine:G.state.data,onCancel:G.close,onSuccess:()=>{G.close(),ce()}}),e.jsx(Le,{open:_,machines:ae.filter(e=>P.includes(e.machineName)),onCancel:()=>B(!1),onSuccess:()=>{B(!1),O([]),ce()}}),e.jsx(Ge,{open:Q,machines:ae.filter(e=>P.includes(e.machineName)),onCancel:()=>X(!1),onSuccess:()=>{X(!1),O([]),ce()}}),e.jsx(_e,{open:U,machines:ae.filter(e=>P.includes(e.machineName)),onCancel:()=>K(!1)}),!h&&e.jsx(Ve,{machine:Z,visible:Y,onClose:be})]})},Yt=ce.div`
  display: flex;
  height: 100%;
  width: 100%;
  position: relative;
  overflow: hidden;
`,ea=ce.div`
  width: ${({$width:e})=>e};
  height: 100%;
  overflow: auto;
  min-width: 300px;
  transition: width 0.3s ease-in-out;
`,ta=ce.div`
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
`,aa=t=>{const{type:i,selectedResource:n,onResourceSelect:s,isPanelCollapsed:r=!0,onTogglePanelCollapse:o}=t,c=Fe(),[l,m]=a.useState(c),[d,u]=a.useState(!1),[h,p]=a.useState(!1);a.useEffect(()=>{m(c)},[c]),a.useEffect(()=>{if(!n){u(!1);const e=setTimeout(()=>{p(!1)},250);return()=>clearTimeout(e)}p(!0),requestAnimationFrame(()=>{u(!0)})},[n]);const g=e=>{s(e)},x=()=>{s(null)},y=r?Pe.COLLAPSED_WIDTH:l;if("machine"===i){const a=n?`calc(100% - ${y}px)`:"100%";return e.jsxs(Yt,{"data-testid":"split-resource-view-container",children:[e.jsx(ea,{$width:a,"data-testid":"split-resource-view-left-panel",children:e.jsx(Jt,{...t,onRowClick:g,selectedMachine:n})}),h&&e.jsx(ta,{$visible:d,$rightOffset:y,onClick:x,"data-testid":"split-resource-view-backdrop"}),n&&e.jsx(Oe,{type:"machineName"in n?"machine":"repositoryName"in n?"repository":"container",data:n,visible:!0,onClose:x,splitWidth:l,onSplitWidthChange:m,isCollapsed:r,onToggleCollapse:o,collapsedWidth:Pe.COLLAPSED_WIDTH})]})}return null},ia=()=>{const{t:t}=$e(["resources","machines","common"]),[n,r]=Ne.useModal(),o=s(),c=i(),l=de(),{teams:m,selectedTeams:d,setSelectedTeams:u,isLoading:h}=Je(),{modalState:p,currentResource:g,openModal:y,closeModal:f}=Ze("machine"),[b,j]=a.useState(null),[v,N]=a.useState(null),[$,w]=a.useState(null),[C,S]=a.useState(!0),[M,B]=a.useState({}),{state:H,open:q,close:K}=I(),Z=k(),{data:J=[],refetch:Y}=Se(d.length>0?d:void 0,d.length>0),{data:ee=[]}=Me(d.length>0?d:void 0),{data:ae=[]}=Q(d.length>0?d:void 0),ie=Ie(),ne=Te(),se=Re(),re=Ae(),oe=Ee(),{executeAction:ce,isExecuting:le}=te();a.useEffect(()=>{const e=o.state;e?.createRepository&&c("/credentials",{state:e,replace:!0})},[o,c]);const me=e=>{j(e),e&&(N(null),w(null),S(!1))},ue=a.useCallback(e=>{et({modal:n,t:t,resourceType:"machine",resourceName:e.machineName,translationNamespace:"machines",onConfirm:()=>re.mutateAsync({teamName:e.teamName,machineName:e.machineName}),onSuccess:()=>Y()})},[re,n,Y,t]),he=a.useCallback(async e=>{try{if("create"===p.mode){const{autoSetup:i,...n}=e;if(await ie.mutateAsync(n),x("success",t("machines:createSuccess")),i)try{await new Promise(e=>setTimeout(e,500));const a=await ce({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,functionName:"setup",params:{datastore_size:"95%",source:"apt-repo",rclone_source:"install-script",docker_source:"docker-repo",install_amd_driver:"auto",install_nvidia_driver:"auto"},priority:3,description:`Auto-setup for machine ${e.machineName}`,addedVia:"machine-creation-auto-setup",machineVault:e.machineVault||"{}"});a.success&&(a.taskId?(x("info",t("machines:setupQueued")),q(a.taskId,e.machineName)):a.isQueued&&x("info",t("machines:setupQueuedForSubmission")))}catch(a){x("warning",t("machines:machineCreatedButSetupFailed"))}f(),Y()}else if(g){const t=g.machineName,a=e.machineName;a&&a!==t&&await ne.mutateAsync({teamName:g.teamName,currentMachineName:t,newMachineName:a}),e.bridgeName&&e.bridgeName!==g.bridgeName&&await se.mutateAsync({teamName:g.teamName,machineName:a||t,newBridgeName:e.bridgeName});const i=e.machineVault;i&&i!==g.vaultContent&&await oe.mutateAsync({teamName:g.teamName,machineName:a||t,machineVault:i,vaultVersion:g.vaultVersion+1}),f(),Y()}}catch(a){}},[f,ie,g,ce,q,Y,t,p.mode,se,ne,oe]),pe=a.useCallback(async(e,t)=>{if(g)try{await oe.mutateAsync({teamName:g.teamName,machineName:g.machineName,machineVault:e,vaultVersion:t}),f(),Y()}catch(a){}},[f,g,Y,oe]),ge=a.useCallback(async e=>{if(g)try{const a=g.machineName,i=g.bridgeName,n=m.find(e=>e.teamName===g.teamName),s={teamName:g.teamName,machineName:a,bridgeName:i,functionName:e.function.name,params:e.params,priority:e.priority,description:e.description,addedVia:"machine-table",teamVault:n?.vaultContent||"{}",machineVault:g.vaultContent||"{}"};if(e.params.repo){const t=ee.find(t=>t.repositoryGuid===e.params.repo);s.repositoryGuid=t?.repositoryGuid||e.params.repo,s.repositoryVault=t?.vaultContent||"{}"}else s.repositoryVault="{}";if("pull"===e.function.name){if("machine"===e.params.sourceType&&e.params.from){const t=J.find(t=>t.machineName===e.params.from);t?.vaultContent&&(s.sourceMachineVault=t.vaultContent)}if("storage"===e.params.sourceType&&e.params.from){const t=ae.find(t=>t.storageName===e.params.from);t?.vaultContent&&(s.sourceStorageVault=t.vaultContent)}}const r=await ce(s);f(),r.success?r.taskId?(x("success",t("machines:queueItemCreated")),q(r.taskId,a)):r.isQueued&&x("info",t("resources:messages.highestPriorityQueued",{resourceType:"machine"})):x("error",r.error||t("resources:errors.failedToCreateQueueItem"))}catch(a){x("error",t("resources:errors.failedToCreateQueueItem"))}},[f,g,ce,J,q,ee,ae,t,m]),xe=ie.isPending||ne.isPending||se.isPending||le,ye=oe.isPending;return e.jsxs(e.Fragment,{children:[e.jsx(T,{children:e.jsxs(R,{children:[e.jsx(A,{level:3,children:t("machines:heading",{defaultValue:"Machines"})}),e.jsxs(E,{children:[e.jsx(D,{children:e.jsxs(V,{children:[e.jsx(F,{children:e.jsx(P,{children:e.jsx(Ye,{"data-testid":"machines-team-selector",teams:m,selectedTeams:d,onChange:u,loading:h,placeholder:t("teams.selectTeamToView"),style:{width:"100%"}})})}),d.length>0&&e.jsxs(O,{children:[e.jsx(fe,{title:t("machines:createMachine"),children:e.jsx(z,{$variant:"primary",icon:e.jsx(L,{}),"data-testid":"machines-create-machine-button",onClick:()=>y("create"),"aria-label":t("machines:createMachine")})}),e.jsx(fe,{title:t("machines:connectivityTest"),children:e.jsx(z,{icon:e.jsx(W,{}),"data-testid":"machines-connectivity-test-button",onClick:()=>Z.open(),disabled:0===J.length,"aria-label":t("machines:connectivityTest")})}),e.jsx(fe,{title:t("common:actions.refresh"),children:e.jsx(z,{icon:e.jsx(_,{}),"data-testid":"machines-refresh-button",onClick:()=>{Y(),B(e=>({...e,_global:Date.now()}))},"aria-label":t("common:actions.refresh")})})]})]})}),e.jsx(G,{children:0===d.length?e.jsx(be,{image:be.PRESENTED_IMAGE_SIMPLE,description:t("teams.selectTeamPrompt"),style:{padding:`${l.spacing.LG}px 0`}}):e.jsx(aa,{type:"machine",teamFilter:d,showFilters:!0,showActions:!0,onCreateMachine:()=>y("create"),onEditMachine:e=>y("edit",e),onVaultMachine:e=>y("vault",e),onFunctionsMachine:(e,t)=>{y("create",e,t),B(t=>({...t,[e.machineName]:Date.now()}))},onDeleteMachine:ue,enabled:d.length>0,refreshKeys:M,onQueueItemCreated:(e,t)=>{q(e,t)},selectedResource:b||v||$,onResourceSelect:e=>{e&&"machineName"in e?me(e):e&&"repositoryName"in e?(me(null),N(e),w(null),S(!1)):e&&"id"in e&&"state"in e?(me(null),N(null),w(e),S(!1)):(me(null),N(null),w(null))},isPanelCollapsed:C,onTogglePanelCollapse:()=>{S(e=>!e)}})})]})]})}),e.jsx(X,{"data-testid":"machines-machine-modal",open:p.open,onCancel:f,resourceType:"machine",mode:p.mode,existingData:p.data||g,teamFilter:d.length>0?d:void 0,preselectedFunction:p.preselectedFunction,onSubmit:he,onUpdateVault:"edit"===p.mode?pe:void 0,onFunctionSubmit:ge,isSubmitting:xe,isUpdatingVault:ye,functionCategories:["machine","backup"],hiddenParams:[],defaultParams:{}}),e.jsx(U,{"data-testid":"machines-queue-trace-modal",taskId:H.taskId,open:H.open,onCancel:()=>{const e=H.machineName;K(),e&&B(t=>({...t,[e]:Date.now()})),Y()}}),e.jsx(Ct,{"data-testid":"machines-connectivity-test-modal",open:Z.isOpen,onClose:Z.close,machines:J,teamFilter:d}),r]})};export{ia as default};
