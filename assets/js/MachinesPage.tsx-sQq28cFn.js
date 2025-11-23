import{j as e,u as t}from"./chunk-jIVxg-O4.js";import{r as a,j as i,R as n,u as s}from"./chunk-DaihG_v-.js";import{B as r,M as o,d as c,e as l,f as m,C as d,b as u,s as h,g as p,D as g,H as x,h as y,i as f,T as b,G as j,I as v,c as N,P as k,j as $,k as w,l as S,m as C,n as M,A as I,o as T,p as R,q as E}from"../index-DyTMMCCu.js";import{R as A}from"./chunk-DsEpBzqB.js";import{u as D,a as V,W as F}from"./chunk-E8fNeJFG.js";import{u as O,a as P,U as z}from"./chunk-B1a7aEc-.js";import{D as G,R as L,Q as _}from"./chunk-BQ6BDo4E.js";import{S as B}from"./chunk-Dmz47Zc8.js";import{C as W}from"./chunk-DAof0Roy.js";import{u as H}from"./chunk-DRRDTZI7.js";import{u as Q,a as X}from"./chunk-BlvZmqj7.js";import{w as q,R as U}from"./chunk-3mr15tdL.js";import{d as K,m as Z,l as J,n as Y}from"./chunk-CsUqxJyM.js";import{T as ee,c as te,B as ae,P as ie,h as ne,a as se,l as re,E as oe,C as ce,g as le,D as me,F as de,M as ue}from"./chunk-BKxIVqYm.js";import{u as he}from"./chunk-DfOmacDz.js";import{C as pe}from"./chunk-q5ZU0FS3.js";import{B as ge}from"./chunk-8OjREMlW.js";import{u as xe,a as ye,b as fe,c as be,d as je,e as ve,f as Ne}from"./chunk-DGPlsbDZ.js";import{A as ke}from"./chunk-C-Kc5vcl.js";import{M as $e,u as we,U as Se}from"./chunk-DuqDGdjK.js";import{M as Ce,A as Me,R as Ie,V as Te}from"./chunk-CKJxWdbn.js";import{a as Re,c as Ee,E as Ae}from"./chunk-oGC6pvo6.js";import{D as De,E as Ve,L as Fe}from"./chunk-BiBu7VRd.js";import{F as Oe}from"./chunk-DTOrZrGm.js";import{T as Pe}from"./chunk-IumuMkqo.js";import"./chunk-BaNBjVcO.js";import"./chunk-EExu6BjB.js";import"./chunk-Om7cwAMr.js";import"./chunk-BWpuTwnl.js";import"./chunk-Bf4c4E-m.js";import"./chunk-OvtUXaj_.js";import"./chunk-CBWvV4xV.js";import"./chunk-BEnbFgXi.js";import"./chunk-DkL1piM8.js";import"./chunk-Di9Qi2wT.js";import"./chunk-CZUXR2Dk.js";import"./chunk-DVhBN_BK.js";import"./chunk-B89P9exN.js";import"./chunk-g3JiB1MS.js";import"./chunk-Kje2sC16.js";import"./chunk-DaCgadqX.js";import"./chunk-BBKOdXHR.js";import"./forkTokenService.ts-BbmGFlk5.js";import"./chunk-DeRY2Py9.js";function ze(e){const{buildQueueVault:t}=D();Q();const i=H(),{data:n}=V(),s=a.useCallback(async e=>{try{const a=function(e,t){if(e.teamVault&&"{}"!==e.teamVault)return e.teamVault;const a=t?.find(t=>t.teamName===e.teamName);return a?.vaultContent||"{}"}(e,n),s=await async function(e,t,a){const i=4,n="Ping connectivity test",s="ping-service",r="{}";return a({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,functionName:"ping",params:{},priority:e.priority||i,description:e.description||n,addedVia:e.addedVia||s,machineVault:e.machineVault||r,teamVault:t,repositoryVault:e.repositoryVault||r})}(e,a,t),r=await async function(e,t,a){const i=4;return a.mutateAsync({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,queueVault:t,priority:e.priority||i})}(e,s,i);return{taskId:r?.taskId,success:!!r?.taskId||!!r?.isQueued}}catch(a){return{success:!1,error:a.message||"Failed to execute ping function"}}},[t,i,n]),r=a.useCallback(async(e,t)=>s({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,priority:t?.priority,description:t?.description,addedVia:t?.addedVia,machineVault:e.vaultContent||"{}"}),[s]),o=a.useCallback(async(e,t)=>{const a=await s(e);if(!a.success||!a.taskId)return a;const i=await q(a.taskId,t);return{...a,completionResult:i,success:i.success,error:i.success?void 0:i.message}},[s]),c=a.useCallback(async(e,t)=>o({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,priority:t?.priority,description:t?.description,addedVia:t?.addedVia,machineVault:e.vaultContent||"{}"},t?.timeout),[o]);return{executePing:s,executePingForMachine:r,executePingAndWait:o,executePingForMachineAndWait:c,waitForQueueItemCompletion:q,isLoading:i.isPending}}const{Text:Ge}=ee,Le=Z`
  0% {
    opacity: 0.65;
  }
  50% {
    opacity: 1;
  }
  100% {
    opacity: 0.65;
  }
`,_e=K(r)`
  .ant-modal-body {
    padding: ${({theme:e})=>e.spacing.XL}px;
  }
`,Be=K(o)`
  width: 100%;
`,We=K.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.LG}px;
`,He=K(te)`
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
`,Qe=K.div`
  display: flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,Xe=K(ae)`
  && {
    min-width: ${({theme:e})=>2*e.spacing.XXL}px;
    min-height: ${({theme:e})=>e.dimensions.CONTROL_HEIGHT}px;
    font-size: ${({theme:e})=>e.fontSize.SM}px;
    border-radius: ${({theme:e})=>e.borderRadius.MD}px;
  }
`,qe=K(ae)`
  && {
    min-width: ${({theme:e})=>e.dimensions.CONTROL_HEIGHT}px;
    min-height: ${({theme:e})=>e.dimensions.CONTROL_HEIGHT}px;
    border-radius: ${({theme:e})=>e.borderRadius.LG}px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,Ue=K.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XS}px;
`,Ke=K(ie)`
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
`,Ze=K(Ge)`
  && {
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    color: ${({theme:e})=>e.colors.textSecondary};
  }
`,Je=K(ne)`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.LG}px;
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,Ye=K.div`
  padding: ${({theme:e})=>e.spacing.MD}px;
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
  background-color: ${({theme:e})=>e.colors.bgSecondary};
`,et=K.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({theme:e})=>e.spacing.XL}px;
`,tt=K.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XS}px;
`,at=K(Ge)`
  && {
    color: ${({theme:e})=>e.colors.textSecondary};
  }
`,it=K(Ge)`
  && {
    color: ${({theme:e,$variant:t})=>"success"===t?e.colors.success:"error"===t?e.colors.error:e.colors.textPrimary};
    font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
  }
`,nt=K(c)`
  .status-testing td {
    animation: ${Le} ${({theme:e})=>e.transitions.SLOW};
    background-color: ${({theme:e})=>e.colors.primaryBg};
  }

  .status-success td {
    background-color: ${({theme:e})=>e.colors.bgSuccess};
  }

  .status-failed td {
    background-color: ${({theme:e})=>e.colors.bgError};
  }
`,st=K.div`
  display: inline-flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,rt=K(Ge)`
  && {
    font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
  }
`,ot=K.span`
  display: inline-flex;
  align-items: center;
  color: ${({theme:e,$variant:t})=>{switch(t){case"success":return e.colors.success;case"failed":return e.colors.error;case"testing":return e.colors.primary;default:return e.colors.textSecondary}}};

  .anticon {
    font-size: ${({theme:e})=>e.fontSize.LG}px;
  }
`,ct=K(se)`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.MD}px;
    border-color: ${({theme:e})=>e.colors.borderSecondary};
    color: ${({theme:e})=>e.colors.textPrimary};
    background-color: ${({theme:e})=>e.colors.bgSecondary};
  }
`,lt=K(l)`
  && {
    text-transform: capitalize;
  }
`,mt=K(Ge)`
  && {
    color: ${({theme:e,$isError:t})=>t?e.colors.error:e.colors.textPrimary};
  }
`,dt=({open:t,onClose:i,machines:n})=>{const{t:s}=he(["machines","common"]),[r,o]=a.useState([]),[c,l]=a.useState(!1),[p,g]=a.useState(0),[x,y]=a.useState(-1),{executePingForMachine:f,waitForQueueItemCompletion:b}=ze();a.useEffect(()=>{if(t&&n.length>0){const e=n.map(e=>({machineName:e.machineName,teamName:e.teamName,bridgeName:e.bridgeName,status:"pending"}));o(e),g(0),y(-1)}},[t,n]);const j=e=>e.success?s("machines:connectionSuccessful"):"TIMEOUT"===e.status?s("machines:testTimeout"):e.message||s("machines:connectionFailed"),v=async(e,t)=>{const a=Date.now();o(e=>e.map((e,a)=>a===t?{...e,status:"testing",timestamp:(new Date).toISOString()}:e));try{const i=await f(e,{priority:4,description:"Connectivity test",addedVia:"connectivity-test"});if(!i.success||!i.taskId)throw new Error(i.error||"Failed to create test task");{o(e=>e.map((e,a)=>a===t?{...e,taskId:i.taskId}:e));const e=await b(i.taskId),n=Date.now()-a;o(a=>a.map((a,i)=>i===t?{...a,status:e.success?"success":"failed",message:j(e),duration:n}:a))}}catch(i){const e=i instanceof Error?i.message:"Failed to create test task",n=Date.now()-a;o(a=>a.map((a,i)=>i===t?{...a,status:"failed",message:e,duration:n}:a))}},N={pending:"neutral",testing:"processing",success:"success",failed:"error"},k=[{title:s("machines:machineName"),dataIndex:"machineName",key:"machineName",render:(t,a)=>e.jsxs(st,{"data-testid":`connectivity-machine-${t}`,children:[e.jsx(ot,{$variant:a.status,children:(()=>{switch(a.status){case"testing":return e.jsx(B,{spin:!0,"data-testid":`connectivity-status-icon-testing-${t}`});case"success":return e.jsx(u,{"data-testid":`connectivity-status-icon-success-${t}`});case"failed":return e.jsx(W,{"data-testid":`connectivity-status-icon-failed-${t}`});default:return e.jsx(d,{"data-testid":`connectivity-status-icon-pending-${t}`})}})()}),e.jsx(rt,{children:t})]})},{title:s("machines:team"),dataIndex:"teamName",key:"teamName",render:t=>e.jsx(ct,{children:t})},{title:s("machines:bridge"),dataIndex:"bridgeName",key:"bridgeName",render:t=>e.jsx(ct,{children:t})},{title:s("machines:status"),dataIndex:"status",key:"status",width:120,render:(t,a)=>{const i={pending:s("machines:pending"),testing:s("machines:testing"),success:s("machines:connected"),failed:s("machines:failed")};return e.jsx(lt,{$variant:N[t],"data-testid":`connectivity-status-tag-${a.machineName}-${t}`,children:i[t]})}},{title:s("machines:responseTime"),dataIndex:"duration",key:"duration",width:120,render:e=>e?e<1e3?`${e}ms`:`${(e/1e3).toFixed(1)}s`:"-"},{title:s("machines:message"),dataIndex:"message",key:"message",ellipsis:!0,render:(t,a)=>t?e.jsx(mt,{$isError:"failed"===a.status,children:t}):"-"}];return e.jsx(_e,{"data-testid":"connectivity-modal",title:e.jsxs(He,{children:[e.jsx(F,{}),s("machines:connectivityTest")]}),open:t,onCancel:i,className:m.ExtraLarge,destroyOnHidden:!0,footer:e.jsxs(Qe,{children:[e.jsx(Xe,{type:"primary",icon:e.jsx(B,{}),onClick:async()=>{l(!0);for(let a=0;a<n.length;a++)y(a),g(Math.round(a/n.length*100)),await v(n[a],a);g(100),l(!1),y(-1);const e=r.filter(e=>"success"===e.status).length,t=r.filter(e=>"failed"===e.status).length;0===t?h("success",s("machines:allMachinesConnected",{count:e})):h("warning",s("machines:machinesConnectedWithFailures",{successCount:e,failedCount:t}))},disabled:c||0===n.length,loading:c,"data-testid":"connectivity-run-test-button",children:s(c?"machines:testing":"machines:runTest")}),e.jsx(re,{title:"Close",children:e.jsx(qe,{icon:e.jsx(W,{}),onClick:i,"data-testid":"connectivity-close-button","aria-label":"Close"})})]}),children:e.jsx(Be,{children:e.jsxs(We,{children:[c&&e.jsxs(Ue,{"data-testid":"connectivity-progress-container",children:[e.jsx(Ke,{percent:p,status:"active","data-testid":"connectivity-progress-bar"}),x>=0&&x<n.length&&e.jsx(Ze,{"data-testid":"connectivity-progress-text",children:s("machines:testingMachine",{machineName:n[x].machineName})})]}),e.jsx(Je,{message:s("machines:connectivityTestDescription"),type:"info",showIcon:!0,icon:e.jsx(F,{}),"data-testid":"connectivity-info-alert"}),e.jsx(nt,{columns:k,dataSource:r,rowKey:"machineName",pagination:!1,scroll:{y:400},loading:0===n.length,rowClassName:e=>`status-${e.status}`,"data-testid":"connectivity-results-table"}),!c&&r.some(e=>"pending"!==e.status)&&e.jsx(Ye,{"data-testid":"connectivity-summary-statistics",children:e.jsxs(et,{children:[e.jsxs(tt,{"data-testid":"connectivity-total-machines",children:[e.jsxs(at,{children:[s("machines:totalMachines"),":"]}),e.jsx(it,{children:n.length})]}),e.jsxs(tt,{"data-testid":"connectivity-connected-count",children:[e.jsxs(at,{children:[s("machines:connected"),":"]}),e.jsx(it,{$variant:"success",children:r.filter(e=>"success"===e.status).length})]}),e.jsxs(tt,{"data-testid":"connectivity-failed-count",children:[e.jsxs(at,{children:[s("machines:failed"),":"]}),e.jsx(it,{$variant:"error",children:r.filter(e=>"failed"===e.status).length})]}),e.jsxs(tt,{"data-testid":"connectivity-average-response",children:[e.jsxs(at,{children:[s("machines:averageResponse"),":"]}),e.jsx(it,{children:(()=>{const e=r.filter(e=>"success"===e.status&&e.duration);if(0===e.length)return"-";const t=e.reduce((e,t)=>e+(t.duration||0),0)/e.length;return t<1e3?`${Math.round(t)}ms`:`${(t/1e3).toFixed(1)}s`})()})]})]})})]})})})},ut={team:{background:"var(--color-success)",color:"var(--color-text-inverse)"},bridge:{background:"var(--color-primary)",color:"var(--color-text-inverse)"},region:{background:"var(--color-info)",color:"var(--color-text-inverse)"},repository:{background:"var(--color-secondary)",color:"var(--color-text-inverse)"},status:{background:"var(--color-warning)",color:"var(--color-text-inverse)"},grand:{background:"var(--color-secondary)",color:"var(--color-text-inverse)"}},ht=K.div`
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
`,pt=K.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
`,gt=K.div`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
  padding: ${({theme:e})=>e.spacing.SM}px ${({theme:e})=>e.spacing.MD}px;
  background-color: var(--color-bg-secondary);
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border: 1px solid var(--color-border-secondary);
  gap: ${({theme:e})=>e.spacing.MD}px;
`,xt=K.span`
  font-weight: 600;
  color: var(--color-text-primary);
`,yt=K.div`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
`,ft=K(ae)`
  && {
    min-width: 42px;
    height: ${p.DIMENSIONS.CONTROL_HEIGHT_SM}px;
    border-radius: ${({theme:e})=>e.borderRadius.SM}px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
`,bt=K.span`
  width: 1px;
  height: 24px;
  background-color: var(--color-border-secondary);
  margin: 0 ${({theme:e})=>e.spacing.SM}px;
`,jt=K(oe).attrs({image:oe.PRESENTED_IMAGE_SIMPLE})`
  margin-top: ${({theme:e})=>e.spacing.XL}px;
`,vt=K.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XL}px;
`,Nt=K(ce)`
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
`,kt=K.div`
  display: flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
  padding: ${({theme:e})=>e.spacing.XS}px 0;
`,$t=K.div`
  width: 4px;
  height: ${p.DIMENSIONS.ICON_XL}px;
  border-radius: ${({theme:e})=>e.borderRadius.SM}px;
  background-color: ${({$color:e})=>e||"var(--color-text-secondary)"};
`,wt=K.span`
  font-size: 18px;
  font-weight: 700;
  color: var(--color-text-primary);
`,St=K.span`
  font-size: 14px;
  color: var(--color-text-secondary);
`,Ct=K.div`
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
`,Mt=K.div`
  display: flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.LG}px;
`,It=K(g)`
  font-size: ${p.DIMENSIONS.ICON_MD}px;
  color: var(--color-primary);
`,Tt=K(It)`
  font-size: ${p.DIMENSIONS.ICON_LG}px;
`,Rt=K.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XS}px;
`,Et=K.span`
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
`,At=K(ae)`
  && {
    /* Maintain compact pill styling to mirror historical control surface */
    height: ${p.DIMENSIONS.CONTROL_HEIGHT_SM}px;
    border-radius: ${({theme:e})=>e.borderRadius.SM}px;
    display: inline-flex;
    align-items: center;
    gap: ${({theme:e})=>e.spacing.XS}px;
  }
`,Dt=K.span`
  font-size: 18px;
  color: ${({$status:e})=>{switch(e){case"online":return"var(--color-success)";case"offline":return"var(--color-text-tertiary)";default:return"var(--color-text-quaternary)"}}};
  display: inline-flex;
  align-items: center;
  justify-content: center;
`,Vt=K(se)`
  && {
    border: none;
    border-radius: ${({theme:e})=>e.borderRadius.MD}px;
    font-weight: 500;
    display: inline-flex;
    align-items: center;
    gap: ${({theme:e})=>e.spacing.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.SM}px;
    line-height: 24px;
    background-color: ${({$variant:e})=>ut[e].background};
    color: ${({$variant:e})=>ut[e].color};
  }
`,Ft=K(Vt)`
  && {
    font-size: 16px;
    padding: 4px ${({theme:e})=>e.spacing.MD}px;
  }
`,Ot=K(le)`
  && .ant-badge-count {
    background-color: ${({$isPositive:e})=>e?"var(--color-success)":"var(--color-border-secondary)"};
    color: ${({$isPositive:e})=>e?"var(--color-text-inverse)":"var(--color-text-secondary)"};
  }
`,Pt=({teamFilter:s,showActions:r=!0,className:o="",onEditMachine:c,onFunctionsMachine:l,onDeleteMachine:m,enabled:d=!0,onQueueItemCreated:k,onRowClick:$,selectedMachine:w})=>{const{t:S}=he(["machines","common","functions","resources"]),C=i(),M=t(e=>e.ui.uiMode),I="expert"===M,{executePingForMachineAndWait:T}=ze(),R=a.useRef(null),[E,A]=a.useState("machine"),[D,V]=a.useState([]),[P,z]=a.useState({open:!1,entityType:null,entityIdentifier:null}),[_,B]=a.useState({open:!1,machine:null}),[W,H]=a.useState({open:!1,machine:null}),[Q,X]=a.useState(!1),[q,K]=a.useState(!1),[Z,Y]=a.useState(!1),[ee,ie]=a.useState(null),[ne,se]=a.useState(!1);n.useEffect(()=>{"simple"===M&&"machine"!==E&&A("machine")},[M,E]);const{data:oe=[],isLoading:ce,refetch:le}=xe(s,d),{data:ue=[]}=ye(s),fe=((e,t={})=>{const{rowHeight:i=54,headerHeight:n=55,paginationHeight:s=64,containerOffset:r=32,minRows:o=5,maxRows:c=100}=t,[l,m]=a.useState(10),d=a.useRef(null),u=a.useCallback(()=>{if(!e.current)return;const t=e.current.offsetHeight-n-s-r,a=Math.floor(t/i),l=Math.max(o,Math.min(c,a));m(l)},[e,i,n,s,r,o,c]),h=a.useRef(null);return a.useEffect(()=>(h.current=J.debounce(u,300),()=>{h.current?.cancel()}),[u]),a.useEffect(()=>(u(),e.current&&window.ResizeObserver&&(d.current=new ResizeObserver(()=>{h.current?.()}),d.current.observe(e.current)),()=>{d.current&&d.current.disconnect(),h.current?.cancel()}),[u,e]),l})(R,{containerOffset:170,minRows:5,maxRows:50}),be=oe,je=e=>{try{if(!e.vaultStatus||e.vaultStatus.trim().startsWith("jq:")||e.vaultStatus.trim().startsWith("error:")||!e.vaultStatus.trim().startsWith("{"))return[];const t=JSON.parse(e.vaultStatus);if("completed"===t.status&&t.result){let e=t.result;if(e.match(/(\}[\s\n]*$)/)){const t=e.lastIndexOf("}");t<e.length-10&&(e=e.substring(0,t+1))}const a=e.indexOf("\njq:");a>0&&(e=e.substring(0,a)),e=e.trim();const i=JSON.parse(e);if(i?.repositories&&Array.isArray(i.repositories))return i.repositories.map(e=>{if(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(e.name)){const t=ue.find(t=>t.repositoryGuid===e.name);if(t)return{...e,name:t.repositoryName,repositoryGuid:t.repositoryGuid,grandGuid:t.grandGuid}}return e})}}catch(t){}return[]},ve=a.useCallback(e=>{m&&m(e)},[m]),Ne=a.useCallback(e=>{$?$(e):(ie(e),se(!0))},[$]),we=a.useCallback(()=>{se(!1),ie(null)},[]),{getFunctionsByCategory:Se}=O(),Pe=a.useMemo(()=>Se("machine").filter(e=>e&&!1!==e.showInMenu&&"mount"!==e.name&&"pull"!==e.name),[Se]),Ge=I&&f.isEnabled("assignToCluster"),Le=n.useMemo(()=>(({t:t,isExpertMode:a,uiMode:i,showActions:n,hasSplitView:s,canAssignToCluster:r,onEditMachine:o,onFunctionsMachine:c,handleDelete:l,handleRowClick:m,executePingForMachineAndWait:d,setAssignClusterModal:g,setAuditTraceModal:f,machineFunctions:b})=>{const j=[];return j.push({title:t("machines:status"),dataIndex:"vaultStatusTime",key:"status",width:100,align:"center",sorter:Re(e=>{if(!e.vaultStatusTime)return 1/0;const t=new Date(e.vaultStatusTime+"Z");return((new Date).getTime()-t.getTime())/6e4<=3?0:1}),render:(a,i)=>{if(!i.vaultStatusTime)return e.jsx(re,{title:t("machines:statusUnknown"),children:e.jsx(Dt,{$status:"unknown",children:e.jsx(De,{})})});const n=new Date(i.vaultStatusTime+"Z"),s=((new Date).getTime()-n.getTime())/6e4<=3;return e.jsx(re,{title:t(s?"machines:connected":"machines:connectionFailed"),children:e.jsx(Dt,{$status:s?"online":"offline",children:s?e.jsx(u,{}):e.jsx(De,{})})})}},{title:t("machines:machineName"),dataIndex:"machineName",key:"machineName",ellipsis:!0,sorter:Ee("machineName"),render:t=>e.jsxs(te,{children:[e.jsx(It,{}),e.jsx("strong",{children:t})]})}),s||j.push({title:t("machines:team"),dataIndex:"teamName",key:"teamName",width:150,ellipsis:!0,sorter:Ee("teamName"),render:t=>e.jsx(Vt,{$variant:"team",children:t})}),s||(a?j.push({title:t("machines:region"),dataIndex:"regionName",key:"regionName",width:150,ellipsis:!0,sorter:Ee("regionName"),render:t=>t?e.jsx(Vt,{$variant:"region",children:t}):"-"},{title:t("machines:bridge"),dataIndex:"bridgeName",key:"bridgeName",width:150,ellipsis:!0,sorter:Ee("bridgeName"),render:t=>e.jsx(Vt,{$variant:"bridge",children:t})}):"simple"!==i&&j.push({title:t("bridges.bridge"),dataIndex:"bridgeName",key:"bridgeName",width:150,ellipsis:!0,sorter:Ee("bridgeName"),render:t=>e.jsx(Vt,{$variant:"bridge",children:t})})),!s&&r&&j.push({title:t("machines:assignmentStatus.title"),key:"assignmentStatus",width:180,ellipsis:!0,render:(t,a)=>e.jsx(Ce,{machine:a})}),s||j.push({title:t("machines:queueItems"),dataIndex:"queueCount",key:"queueCount",width:100,align:"center",sorter:Ee("queueCount"),render:t=>e.jsx(Ot,{$isPositive:t>0,count:t,showZero:!0})}),n&&j.push({title:t("common:table.actions"),key:"actions",width:p.DIMENSIONS.CARD_WIDTH,render:(a,i)=>e.jsxs(te,{children:[e.jsx(re,{title:t("common:viewDetails"),children:e.jsx(ae,{type:"default",size:"small",icon:e.jsx(Ve,{}),onClick:e=>{e.stopPropagation(),m(i)},"data-testid":`machine-view-details-${i.machineName}`,"aria-label":t("common:viewDetails")})}),e.jsx(re,{title:t("common:actions.edit"),children:e.jsx(ae,{type:"primary",size:"small",icon:e.jsx(Ae,{}),onClick:()=>o&&o(i),"data-testid":`machine-edit-${i.machineName}`,"aria-label":t("common:actions.edit")})}),e.jsx(me,{"data-testid":`machine-dropdown-${i.machineName}`,menu:{items:[{key:"functions",label:t("machines:runAction"),icon:e.jsx(Oe,{}),"data-testid":`machine-functions-${i.machineName}`,children:[...b.filter(e=>!1!==e?.showInMenu).map(t=>({key:`function-${t?.name||"unknown"}`,label:e.jsx("span",{title:t?.description||"",children:t?.name||"Unknown"}),onClick:()=>{c&&t?.name&&c(i,t.name)},"data-testid":`machine-function-${t?.name||"unknown"}-${i.machineName}`})),{type:"divider"},{key:"advanced",label:t("machines:advanced"),icon:e.jsx(Oe,{}),onClick:()=>{c&&c(i)},"data-testid":`machine-advanced-${i.machineName}`}]},{key:"test",label:t("machines:connectivityTest"),icon:e.jsx(F,{}),onClick:async()=>{h("info",t("machines:testingConnection"));const e=await d(i,{priority:4,description:"Connectivity test",addedVia:"machine-table",timeout:15e3});e.success?h("success",t("machines:connectionSuccessful")):h("error",e.error||t("machines:connectionFailed"))},"data-testid":`machine-test-${i.machineName}`},...r?[{key:"assignCluster",label:i.distributedStorageClusterName?t("machines:changeClusterAssignment"):t("machines:assignToCluster"),icon:e.jsx(pe,{}),onClick:()=>{g({open:!0,machine:i})},"data-testid":`machine-assign-cluster-${i.machineName}`}]:[]]},trigger:["click"],children:e.jsx(re,{title:t("machines:remote"),children:e.jsx(ae,{type:"primary",size:"small",icon:e.jsx(Oe,{}),"data-testid":`machine-remote-${i.machineName}`,"aria-label":t("machines:remote")})})}),e.jsx(re,{title:t("machines:trace"),children:e.jsx(ae,{type:"primary",size:"small",icon:e.jsx(x,{}),onClick:()=>{f({open:!0,entityType:"Machine",entityIdentifier:i.machineName,entityName:i.machineName})},"data-testid":`machine-trace-${i.machineName}`,"aria-label":t("machines:trace")})}),e.jsx(re,{title:t("common:actions.delete"),children:e.jsx(ae,{type:"primary",danger:!0,size:"small",icon:e.jsx(y,{}),onClick:()=>l(i),"data-testid":`machine-delete-${i.machineName}`,"aria-label":t("common:actions.delete")})}),e.jsx(Fe,{machine:i.machineName,teamName:i.teamName})]})}),j})({t:S,isExpertMode:I,uiMode:M,showActions:r,hasSplitView:Boolean($),canAssignToCluster:Ge,onEditMachine:c,onFunctionsMachine:l,handleDelete:ve,handleRowClick:Ne,executePingForMachineAndWait:T,setAssignClusterModal:H,setAuditTraceModal:z,machineFunctions:Pe}),[S,I,M,r,$,Ge,c,l,ve,Ne,T,H,z,Pe]),_e=Ge?{selectedRowKeys:D,onChange:e=>{V(e)},getCheckboxProps:e=>({disabled:!1,"data-testid":`machine-checkbox-${e.machineName}`})}:void 0,Be=a.useMemo(()=>{const e={};return"machine"===E||be.forEach(t=>{let a="";if("bridge"===E)a=t.bridgeName;else if("team"===E)a=t.teamName;else if("region"===E)a=t.regionName||"Unknown";else{if("repository"===E){const a=je(t);if(0===a.length)return;return void a.forEach(a=>{const i=a.name;e[i]||(e[i]=[]),e[i].find(e=>e.machineName===t.machineName)||e[i].push(t)})}if("status"===E){const e=je(t);if(0===e.length)a="No Repositories";else{const t=e.some(e=>!e.accessible),i=e.some(e=>e.mounted&&e.docker_running),n=e.some(e=>e.mounted&&!e.docker_running),s=e.some(e=>!e.mounted);a=t?"Inaccessible":i?"Active (Running)":n?"Ready (Stopped)":s?"Not Mounted":"Unknown Status"}}else if("grand"===E){const a=je(t);if(0===a.length)return;return void a.forEach(a=>{let i="No Grand Repository";if(a.grandGuid){const e=ue.find(e=>e.repositoryGuid===a.grandGuid);e&&(i=e.repositoryName)}e[i]||(e[i]=[]),e[i].find(e=>e.machineName===t.machineName)||e[i].push(t)})}}a&&(e[a]||(e[a]=[]),e[a].push(t))}),e},[be,E,ue,je]);return e.jsxs(ht,{className:o,children:["simple"===M?null:e.jsx(yt,{children:e.jsxs(te,{wrap:!0,size:"small",children:[e.jsx(re,{title:S("machines:machine"),children:e.jsx(ft,{type:"machine"===E?"primary":"default",icon:e.jsx(g,{}),onClick:()=>A("machine"),"data-testid":"machine-view-toggle-machine","aria-label":S("machines:machine")})}),e.jsx(bt,{}),e.jsx(re,{title:S("machines:groupByBridge"),children:e.jsx(ft,{type:"bridge"===E?"primary":"default",icon:e.jsx(pe,{}),onClick:()=>A("bridge"),"data-testid":"machine-view-toggle-bridge","aria-label":S("machines:groupByBridge")})}),e.jsx(re,{title:S("machines:groupByTeam"),children:e.jsx(ft,{type:"team"===E?"primary":"default",icon:e.jsx(b,{}),onClick:()=>A("team"),"data-testid":"machine-view-toggle-team","aria-label":S("machines:groupByTeam")})}),I&&e.jsx(re,{title:S("machines:groupByRegion"),children:e.jsx(ft,{type:"region"===E?"primary":"default",icon:e.jsx(j,{}),onClick:()=>A("region"),"data-testid":"machine-view-toggle-region","aria-label":S("machines:groupByRegion")})}),e.jsx(re,{title:S("machines:groupByRepository"),children:e.jsx(ft,{type:"repository"===E?"primary":"default",icon:e.jsx(v,{}),onClick:()=>A("repository"),"data-testid":"machine-view-toggle-repository","aria-label":S("machines:groupByRepository")})}),e.jsx(re,{title:S("machines:groupByStatus"),children:e.jsx(ft,{type:"status"===E?"primary":"default",icon:e.jsx(G,{}),onClick:()=>A("status"),"data-testid":"machine-view-toggle-status","aria-label":S("machines:groupByStatus")})}),e.jsx(re,{title:S("machines:groupByGrand"),children:e.jsx(ft,{type:"grand"===E?"primary":"default",icon:e.jsx(ge,{}),onClick:()=>A("grand"),"data-testid":"machine-view-toggle-grand","aria-label":S("machines:groupByGrand")})})]})}),Ge&&0!==D.length?e.jsxs(gt,{children:[e.jsxs(te,{size:"middle",children:[e.jsx(xt,{children:S("machines:bulkActions.selected",{count:D.length})}),e.jsx(re,{title:S("common:actions.clearSelection"),children:e.jsx(ae,{size:"small",onClick:()=>V([]),"data-testid":"machine-bulk-clear-selection","aria-label":S("common:actions.clearSelection")})})]}),e.jsxs(te,{size:"middle",children:[e.jsx(re,{title:S("machines:bulkActions.assignToCluster"),children:e.jsx(ae,{type:"primary",icon:e.jsx(pe,{}),onClick:()=>X(!0),"data-testid":"machine-bulk-assign-cluster","aria-label":S("machines:bulkActions.assignToCluster")})}),e.jsx(re,{title:S("machines:bulkActions.removeFromCluster"),children:e.jsx(ae,{icon:e.jsx(pe,{}),onClick:()=>K(!0),"data-testid":"machine-bulk-remove-cluster","aria-label":S("machines:bulkActions.removeFromCluster")})}),e.jsx(re,{title:S("machines:bulkActions.viewAssignmentStatus"),children:e.jsx(ae,{icon:e.jsx(N,{}),onClick:()=>Y(!0),"data-testid":"machine-bulk-view-status","aria-label":S("machines:bulkActions.viewAssignmentStatus")})})]})]}):null,"machine"===E?e.jsx(pt,{ref:R,children:e.jsx(de,{columns:Le,dataSource:be,rowKey:"machineName",loading:ce,scroll:{x:"max-content"},rowSelection:_e,rowClassName:e=>{const t="machine-table-row";return w?.machineName===e.machineName?`${t} machine-table-row--selected`:t},"data-testid":"machine-table",pagination:{pageSize:fe,showSizeChanger:!1,showTotal:(e,t)=>S("common:table.showingRecords",{start:t[0],end:t[1],total:e})},onRow:e=>({"data-testid":`machine-row-${e.machineName}`,onClick:t=>{const a=t.target;a.closest("button")||a.closest(".ant-dropdown")||a.closest(".ant-dropdown-menu")||C(`/machines/${e.machineName}/repositories`,{state:{machine:e}})}}),sticky:!0})}):(()=>{if(0===Object.keys(Be).length)return e.jsx(jt,{description:S("resources:repositories.noRepositories")});const t={machine:"repository",bridge:"bridge",team:"team",region:"region",repository:"repository",status:"status",grand:"grand"},a={team:"var(--color-success)",bridge:"var(--color-primary)",region:"var(--color-info)",repository:"var(--color-secondary)",status:"var(--color-warning)",grand:"var(--color-secondary)"},i={bridge:e.jsx(pe,{}),team:e.jsx(b,{}),region:e.jsx(j,{}),repository:e.jsx(v,{}),status:e.jsx(G,{}),grand:e.jsx(ge,{})};return e.jsx(vt,{children:Object.entries(Be).map(([n,s],r)=>{const o=t[E],c=a[o];return e.jsxs(Nt,{$isAlternate:r%2==0,children:[e.jsxs(kt,{children:[e.jsx($t,{$color:c}),e.jsxs(te,{size:"small",children:[e.jsxs(wt,{children:["#",r+1]}),e.jsx(Ft,{$variant:o,icon:i[E],children:n}),e.jsxs(St,{children:[s.length," ",1===s.length?S("machines:machine"):S("machines:machines")]})]})]}),s.map((t,a)=>e.jsxs(Ct,{$isStriped:a%2!=0,onClick:()=>C(`/machines/${t.machineName}/repositories`,{state:{machine:t}}),"data-testid":`grouped-machine-row-${t.machineName}`,children:[e.jsxs(Mt,{children:[e.jsx(Tt,{}),e.jsxs(Rt,{children:[e.jsx(Et,{children:t.machineName}),e.jsxs(te,{size:"small",children:[e.jsx(Vt,{$variant:"team",children:t.teamName}),t.bridgeName&&e.jsx(Vt,{$variant:"bridge",children:t.bridgeName}),t.regionName&&e.jsx(Vt,{$variant:"region",children:t.regionName})]})]})]}),e.jsx(re,{title:S("machines:viewRepositories"),children:e.jsx(At,{type:"primary",icon:e.jsx(L,{}),onClick:e=>{e.stopPropagation(),C(`/machines/${t.machineName}/repositories`,{state:{machine:t}})},children:S("machines:viewRepositories")})})]},t.machineName))]},n)})})})(),e.jsx(ke,{open:P.open,onCancel:()=>z({open:!1,entityType:null,entityIdentifier:null}),entityType:P.entityType,entityIdentifier:P.entityIdentifier,entityName:P.entityName}),_.machine&&e.jsx(U,{open:_.open,onCancel:()=>B({open:!1,machine:null}),machineName:_.machine.machineName,teamName:_.machine.teamName,bridgeName:_.machine.bridgeName,onQueueItemCreated:k}),W.machine&&e.jsx(Me,{open:W.open,machine:W.machine,onCancel:()=>H({open:!1,machine:null}),onSuccess:()=>{H({open:!1,machine:null}),le()}}),e.jsx(Me,{open:Q,machines:oe.filter(e=>D.includes(e.machineName)),onCancel:()=>X(!1),onSuccess:()=>{X(!1),V([]),le()}}),e.jsx(Ie,{open:q,machines:oe.filter(e=>D.includes(e.machineName)),onCancel:()=>K(!1),onSuccess:()=>{K(!1),V([]),le()}}),e.jsx(Te,{open:Z,machines:oe.filter(e=>D.includes(e.machineName)),onCancel:()=>Y(!1)}),!$&&e.jsx($e,{machine:ee,visible:ne,onClose:we})]})},zt=K.div`
  display: flex;
  height: 100%;
  width: 100%;
  position: relative;
  overflow: hidden;
`,Gt=K.div`
  width: ${({$width:e})=>e};
  height: 100%;
  overflow: auto;
  min-width: 300px;
  transition: width 0.3s ease-in-out;
`,Lt=K.div`
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
`,_t=t=>{const{type:i,selectedResource:n,onResourceSelect:s,isPanelCollapsed:r=!0,onTogglePanelCollapse:o}=t,c=we(),[l,m]=a.useState(c),[d,u]=a.useState(!1),[h,p]=a.useState(!1);a.useEffect(()=>{m(c)},[c]),a.useEffect(()=>{if(!n){u(!1);const e=setTimeout(()=>{p(!1)},250);return()=>clearTimeout(e)}p(!0),requestAnimationFrame(()=>{u(!0)})},[n]);const g=e=>{s(e)},x=()=>{s(null)},y=r?50:l;if("machine"===i){const a=n?`calc(100% - ${y}px)`:"100%";return e.jsxs(zt,{"data-testid":"split-resource-view-container",children:[e.jsx(Gt,{$width:a,"data-testid":"split-resource-view-left-panel",children:e.jsx(Pt,{...t,onRowClick:g,selectedMachine:n})}),h&&e.jsx(Lt,{$visible:d,$rightOffset:y,onClick:x,"data-testid":"split-resource-view-backdrop"}),n&&e.jsx(Se,{type:"machineName"in n?"machine":"repositoryName"in n?"repository":"container",data:n,visible:!0,onClose:x,splitWidth:l,onSplitWidthChange:m,isCollapsed:r,onToggleCollapse:o,collapsedWidth:50})]})}return null},Bt=()=>{const{t:n}=he(["resources","machines","common"]),[r,o]=ue.useModal(),c=s(),l=i(),m=t(e=>e.ui.uiMode),d=Y(),[u,p]=a.useState([]),[g,x]=a.useState(null),[y,f]=a.useState(null),[b,j]=a.useState(null),[v,N]=a.useState(!0),[D,O]=a.useState(null),[G,L]=a.useState({}),[B,W]=a.useState({visible:!1,taskId:null,machineName:null}),[H,Q]=a.useState(!1),[q,U]=a.useState({open:!1,resourceType:"machine",mode:"create"}),{data:K,isLoading:Z}=V(),J=K||[],{data:ee=[],refetch:te}=xe(u.length>0?u:void 0,u.length>0),{data:ae=[]}=ye(u.length>0?u:void 0),{data:ie=[]}=P(u.length>0?u:void 0),ne=fe(),se=be(),ce=je(),le=ve(),me=Ne(),{executeAction:de,isExecuting:pe}=X(),ge=a.useRef(!1);a.useEffect(()=>{if(!Z&&!ge.current&&J.length>0)if(ge.current=!0,"simple"===m){const e=J.find(e=>"Private Team"===e.teamName);p([e?.teamName||J[0].teamName])}else p([J[0].teamName])},[Z,J,m]),a.useEffect(()=>{const e=c.state;e?.createRepository&&l("/credentials",{state:e,replace:!0})},[c,l]);const ke=a.useCallback((e,t,a)=>{U({open:!0,resourceType:"machine",mode:e,data:t,preselectedFunction:a}),t&&O(t)},[]),$e=a.useCallback(()=>{U({open:!1,resourceType:"machine",mode:"create"}),O(null)},[]),we=e=>{x(e),e&&(f(null),j(null),N(!1))},Se=a.useCallback(e=>{const t=e.machineName;r.confirm({title:n("machines:confirmDelete"),content:n("machines:deleteWarning",{name:t,machineName:t}),okText:n("common:actions.delete"),okType:"danger",cancelText:n("common:actions.cancel"),onOk:async()=>{try{await le.mutateAsync({teamName:e.teamName,machineName:t}),te(),h("success",n("machines:deleteSuccess"))}catch(a){h("error",n("machines:deleteError"))}}})},[le,r,te,n]),Ce=a.useCallback(async e=>{try{if("create"===q.mode){const{autoSetup:a,...i}=e;if(await ne.mutateAsync(i),h("success",n("machines:createSuccess")),a)try{await new Promise(e=>setTimeout(e,500));const t=await de({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,functionName:"setup",params:{datastore_size:"95%",source:"apt-repo",rclone_source:"install-script",docker_source:"docker-repo",install_amd_driver:"auto",install_nvidia_driver:"auto"},priority:3,description:`Auto-setup for machine ${e.machineName}`,addedVia:"machine-creation-auto-setup",machineVault:e.machineVault||"{}"});t.success&&(t.taskId?(h("info",n("machines:setupQueued")),W({visible:!0,taskId:t.taskId,machineName:e.machineName})):t.isQueued&&h("info",n("machines:setupQueuedForSubmission")))}catch(t){h("warning",n("machines:machineCreatedButSetupFailed"))}$e(),te()}else if(D){const t=D.machineName,a=e.machineName;a&&a!==t&&await se.mutateAsync({teamName:D.teamName,currentMachineName:t,newMachineName:a}),e.bridgeName&&e.bridgeName!==D.bridgeName&&await ce.mutateAsync({teamName:D.teamName,machineName:a||t,newBridgeName:e.bridgeName});const i=e.machineVault;i&&i!==D.vaultContent&&await me.mutateAsync({teamName:D.teamName,machineName:a||t,machineVault:i,vaultVersion:D.vaultVersion+1}),$e(),te()}}catch(t){}},[$e,ne,D,de,te,n,q.mode,ce,se,me]),Me=a.useCallback(async(e,t)=>{if(D)try{await me.mutateAsync({teamName:D.teamName,machineName:D.machineName,machineVault:e,vaultVersion:t}),$e(),te()}catch(a){}},[$e,D,te,me]),Ie=a.useCallback(async e=>{if(D)try{const t=D.machineName,a=D.bridgeName,i=J.find(e=>e.teamName===D.teamName),s={teamName:D.teamName,machineName:t,bridgeName:a,functionName:e.function.name,params:e.params,priority:e.priority,description:e.description,addedVia:"machine-table",teamVault:i?.vaultContent||"{}",machineVault:D.vaultContent||"{}"};if(e.params.repo){const t=ae.find(t=>t.repositoryGuid===e.params.repo);s.repositoryGuid=t?.repositoryGuid||e.params.repo,s.repositoryVault=t?.vaultContent||"{}"}else s.repositoryVault="{}";if("pull"===e.function.name){if("machine"===e.params.sourceType&&e.params.from){const t=ee.find(t=>t.machineName===e.params.from);t?.vaultContent&&(s.sourceMachineVault=t.vaultContent)}if("storage"===e.params.sourceType&&e.params.from){const t=ie.find(t=>t.storageName===e.params.from);t?.vaultContent&&(s.sourceStorageVault=t.vaultContent)}}const r=await de(s);$e(),r.success?r.taskId?(h("success",n("machines:queueItemCreated")),W({visible:!0,taskId:r.taskId,machineName:t})):r.isQueued&&h("info",n("resources:messages.highestPriorityQueued",{resourceType:"machine"})):h("error",r.error||n("resources:errors.failedToCreateQueueItem"))}catch(t){h("error",n("resources:errors.failedToCreateQueueItem"))}},[$e,D,de,ee,ae,ie,n,J]),Te=ne.isPending||se.isPending||ce.isPending||pe,Re=me.isPending;return e.jsxs(e.Fragment,{children:[e.jsx(k,{children:e.jsxs($,{children:[e.jsx(w,{children:e.jsxs(S,{children:[e.jsx(C,{children:e.jsx(M,{children:e.jsx(Pe,{"data-testid":"machines-team-selector",teams:J,selectedTeams:u,onChange:p,loading:Z,placeholder:n("teams.selectTeamToView"),style:{width:"100%"}})})}),u.length>0&&e.jsxs(I,{children:[e.jsx(re,{title:n("machines:createMachine"),children:e.jsx(T,{type:"primary",icon:e.jsx(R,{}),"data-testid":"machines-create-machine-button",onClick:()=>ke("create"),"aria-label":n("machines:createMachine")})}),e.jsx(re,{title:n("machines:connectivityTest"),children:e.jsx(T,{icon:e.jsx(F,{}),"data-testid":"machines-connectivity-test-button",onClick:()=>Q(!0),disabled:0===ee.length,"aria-label":n("machines:connectivityTest")})}),e.jsx(re,{title:n("common:actions.refresh"),children:e.jsx(T,{icon:e.jsx(A,{}),"data-testid":"machines-refresh-button",onClick:()=>{te(),L(e=>({...e,_global:Date.now()}))},"aria-label":n("common:actions.refresh")})})]})]})}),e.jsx(E,{children:0===u.length?e.jsx(oe,{image:oe.PRESENTED_IMAGE_SIMPLE,description:n("teams.selectTeamPrompt"),style:{padding:`${d.spacing.LG}px 0`}}):e.jsx(_t,{type:"machine",teamFilter:u,showFilters:!0,showActions:!0,onCreateMachine:()=>ke("create"),onEditMachine:e=>ke("edit",e),onVaultMachine:e=>ke("vault",e),onFunctionsMachine:(e,t)=>{ke("create",e,t),L(t=>({...t,[e.machineName]:Date.now()}))},onDeleteMachine:Se,enabled:u.length>0,refreshKeys:G,onQueueItemCreated:(e,t)=>{W({visible:!0,taskId:e,machineName:t})},selectedResource:g||y||b,onResourceSelect:e=>{e&&"machineName"in e?we(e):e&&"repositoryName"in e?(we(null),f(e),j(null),N(!1)):e&&"id"in e&&"state"in e?(we(null),f(null),j(e),N(!1)):(we(null),f(null),j(null))},isPanelCollapsed:v,onTogglePanelCollapse:()=>{N(e=>!e)}})})]})}),e.jsx(z,{"data-testid":"machines-machine-modal",open:q.open,onCancel:$e,resourceType:"machine",mode:q.mode,existingData:q.data||D,teamFilter:u.length>0?u:void 0,preselectedFunction:q.preselectedFunction,onSubmit:Ce,onUpdateVault:"edit"===q.mode?Me:void 0,onFunctionSubmit:Ie,isSubmitting:Te,isUpdatingVault:Re,functionCategories:["machine","backup"],hiddenParams:[],defaultParams:{}}),e.jsx(_,{"data-testid":"machines-queue-trace-modal",taskId:B.taskId,visible:B.visible,onClose:()=>{W({visible:!1,taskId:null,machineName:null}),B.machineName&&L(e=>({...e,[B.machineName]:Date.now()})),te()}}),e.jsx(dt,{"data-testid":"machines-connectivity-test-modal",open:H,onClose:()=>Q(!1),machines:ee,teamFilter:u}),o]})};export{Bt as default};
