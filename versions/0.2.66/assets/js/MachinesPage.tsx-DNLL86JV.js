import{j as e,u as t}from"./chunk-DXoLy3RZ.js";import{r as a,j as i,R as n,u as s}from"./chunk-ZRs5Vi2W.js";import{B as r,M as o,d as c,e as l,f as m,C as d,b as u,s as h,g as p,D as g,H as x,h as y,i as f,j as b,k as j,T as v,G as N,I as k,c as $,l as w,P as C,m as S,n as M,o as I,p as T,q as R,A,t as E,v as D,w as V}from"../index-CEPyNj08.js";import{R as F}from"./chunk-CuBbjl3l.js";import{u as O,W as P}from"./chunk-k8RYg0Xv.js";import{u as z,a as L,U as G}from"./chunk-CpwFhtIK.js";import{D as _,R as B,Q as W}from"./chunk-JZKQBdDb.js";import{S as H}from"./chunk-BrNxUcRa.js";import{C as Q}from"./chunk-d2k1KcME.js";import{u as X}from"./chunk-DTdnTl7j.js";import{u as q,a as U}from"./chunk-B64bYTFv.js";import{u as K}from"./chunk-DLxZPlHK.js";import{w as Z,R as Y}from"./chunk-JbYayE2m.js";import{c as J,a as ee,b as te}from"./chunk-DYFPw3WY.js";import{d as ae,m as ie,l as ne,n as se}from"./chunk-BtZST8U3.js";import{T as re,c as oe,B as ce,P as le,h as me,a as de,l as ue,E as he,C as pe,g as ge,F as xe,M as ye}from"./chunk-B6OG5Vq-.js";import{u as fe}from"./chunk-BYo3s0jF.js";import{C as be}from"./chunk-pzS3TSBi.js";import{B as je}from"./chunk-DIZ-olQp.js";import{u as ve,a as Ne,b as ke,c as $e,d as we,e as Ce,f as Se}from"./chunk-DQ7tDOPp.js";import{A as Me}from"./chunk-C3pN3Mkx.js";import{M as Ie,u as Te,U as Re}from"./chunk-COmdcZU8.js";import{M as Ae,A as Ee,R as De,V as Ve}from"./chunk-_i3Sx6yb.js";import"./chunk-Bd12bcfc.js";import{g as Fe}from"./chunk-Ci6vuDOV.js";import{c as Oe,a as Pe}from"./chunk-D-pnIc8j.js";import{D as ze,E as Le,L as Ge}from"./chunk-BEielPm8.js";import{A as _e,u as Be,T as We}from"./chunk-DMO3oEL5.js";import{E as He}from"./chunk-l4qIFyNw.js";import{F as Qe}from"./chunk-DbYlMfix.js";import{u as Xe}from"./chunk-BNvdSKJ_.js";import{c as qe}from"./chunk-BvNT4ZVG.js";import"./chunk-CEpojzdT.js";import"./chunk-CgtckP3U.js";import"./chunk-CuXMF7gg.js";import"./chunk-C5BhxkdT.js";import"./chunk-D9hZugn2.js";import"./chunk-BHjlIAfH.js";import"./chunk-BB7PCzTr.js";import"./chunk-FSRXIBAr.js";import"./chunk-Cqaj9b5f.js";import"./chunk-BRmVlKjS.js";import"./chunk-DhpoEw86.js";import"./chunk-CfR6TlFg.js";import"./chunk-1YaItkzQ.js";import"./chunk-BXgErRVX.js";import"./chunk-0eCq0F_t.js";import"./chunk-CgdDx0H7.js";import"./chunk-CicOgBml.js";import"./forkTokenService.ts-Bh9BXjSX.js";import"./chunk-D83A5xz1.js";function Ue(e){const{buildQueueVault:t}=O();q();const i=X(),{data:n}=K(),s=a.useCallback(async e=>{try{const a=function(e,t){if(e.teamVault&&"{}"!==e.teamVault)return e.teamVault;const a=t?.find(t=>t.teamName===e.teamName);return a?.vaultContent||"{}"}(e,n),s=await async function(e,t,a){const i=4,n="Ping connectivity test",s="ping-service",r="{}";return a({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,functionName:"ping",params:{},priority:e.priority||i,description:e.description||n,addedVia:e.addedVia||s,machineVault:e.machineVault||r,teamVault:t,repositoryVault:e.repositoryVault||r})}(e,a,t),r=await async function(e,t,a){const i=4;return a.mutateAsync({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,queueVault:t,priority:e.priority||i})}(e,s,i);return{taskId:r?.taskId,success:!!r?.taskId||!!r?.isQueued}}catch(a){return{success:!1,error:a.message||"Failed to execute ping function"}}},[t,i,n]),r=a.useCallback(async(e,t)=>s({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,priority:t?.priority,description:t?.description,addedVia:t?.addedVia,machineVault:e.vaultContent||"{}"}),[s]),o=a.useCallback(async(e,t)=>{const a=await s(e);if(!a.success||!a.taskId)return a;const i=await Z(a.taskId,t);return{...a,completionResult:i,success:i.success,error:i.success?void 0:i.message}},[s]),c=a.useCallback(async(e,t)=>o({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,priority:t?.priority,description:t?.description,addedVia:t?.addedVia,machineVault:e.vaultContent||"{}"},t?.timeout),[o]);return{executePing:s,executePingForMachine:r,executePingAndWait:o,executePingForMachineAndWait:c,waitForQueueItemCompletion:Z,isLoading:i.isPending}}const{Text:Ke}=re,Ze=ie`
  0% {
    opacity: 0.65;
  }
  50% {
    opacity: 1;
  }
  100% {
    opacity: 0.65;
  }
`,Ye=ae(r)`
  .ant-modal-body {
    padding: ${({theme:e})=>e.spacing.XL}px;
  }
`,Je=ae(o)`
  width: 100%;
`,et=ae.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.LG}px;
`,tt=ae(oe)`
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
`,at=ae.div`
  display: flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,it=ae(ce)`
  && {
    min-width: ${({theme:e})=>2*e.spacing.XXL}px;
    min-height: ${({theme:e})=>e.dimensions.CONTROL_HEIGHT}px;
    font-size: ${({theme:e})=>e.fontSize.SM}px;
    border-radius: ${({theme:e})=>e.borderRadius.MD}px;
  }
`,nt=ae(ce)`
  && {
    min-width: ${({theme:e})=>e.dimensions.CONTROL_HEIGHT}px;
    min-height: ${({theme:e})=>e.dimensions.CONTROL_HEIGHT}px;
    border-radius: ${({theme:e})=>e.borderRadius.LG}px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,st=ae.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XS}px;
`,rt=ae(le)`
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
`,ot=ae(Ke)`
  && {
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    color: ${({theme:e})=>e.colors.textSecondary};
  }
`,ct=ae(me)`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.LG}px;
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,lt=ae.div`
  padding: ${({theme:e})=>e.spacing.MD}px;
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
  background-color: ${({theme:e})=>e.colors.bgSecondary};
`,mt=ae.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({theme:e})=>e.spacing.XL}px;
`,dt=ae.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XS}px;
`,ut=ae(Ke)`
  && {
    color: ${({theme:e})=>e.colors.textSecondary};
  }
`,ht=ae(Ke)`
  && {
    color: ${({theme:e,$variant:t})=>"success"===t?e.colors.success:"error"===t?e.colors.error:e.colors.textPrimary};
    font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
  }
`,pt=ae(c)`
  .status-testing td {
    animation: ${Ze} ${({theme:e})=>e.transitions.SLOW};
    background-color: ${({theme:e})=>e.colors.primaryBg};
  }

  .status-success td {
    background-color: ${({theme:e})=>e.colors.bgSuccess};
  }

  .status-failed td {
    background-color: ${({theme:e})=>e.colors.bgError};
  }
`,gt=ae.div`
  display: inline-flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,xt=ae(Ke)`
  && {
    font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
  }
`,yt=ae.span`
  display: inline-flex;
  align-items: center;
  color: ${({theme:e,$variant:t})=>{switch(t){case"success":return e.colors.success;case"failed":return e.colors.error;case"testing":return e.colors.primary;default:return e.colors.textSecondary}}};

  .anticon {
    font-size: ${({theme:e})=>e.fontSize.LG}px;
  }
`,ft=ae(de)`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.MD}px;
    border-color: ${({theme:e})=>e.colors.borderSecondary};
    color: ${({theme:e})=>e.colors.textPrimary};
    background-color: ${({theme:e})=>e.colors.bgSecondary};
  }
`;ae(l)`
  && {
    text-transform: capitalize;
  }
`;const bt=ae(Ke)`
  && {
    color: ${({theme:e,$isError:t})=>t?e.colors.error:e.colors.textPrimary};
  }
`,jt=({open:t,onClose:i,machines:n})=>{const{t:s}=fe(["machines","common"]),[r,o]=a.useState([]),[c,l]=a.useState(!1),[p,g]=a.useState(0),[x,y]=a.useState(-1),{executePingForMachine:f,waitForQueueItemCompletion:b}=Ue();a.useEffect(()=>{if(t&&n.length>0){const e=n.map(e=>({machineName:e.machineName,teamName:e.teamName,bridgeName:e.bridgeName,status:"pending"}));o(e),g(0),y(-1)}},[t,n]);const j=e=>e.success?s("machines:connectionSuccessful"):"TIMEOUT"===e.status?s("machines:testTimeout"):e.message||s("machines:connectionFailed"),v=async(e,t)=>{const a=Date.now();o(e=>e.map((e,a)=>a===t?{...e,status:"testing",timestamp:(new Date).toISOString()}:e));try{const i=await f(e,{priority:4,description:"Connectivity test",addedVia:"connectivity-test"});if(!i.success||!i.taskId)throw new Error(i.error||"Failed to create test task");{o(e=>e.map((e,a)=>a===t?{...e,taskId:i.taskId}:e));const e=await b(i.taskId),n=Date.now()-a;o(a=>a.map((a,i)=>i===t?{...a,status:e.success?"success":"failed",message:j(e),duration:n}:a))}}catch(i){const e=i instanceof Error?i.message:"Failed to create test task",n=Date.now()-a;o(a=>a.map((a,i)=>i===t?{...a,status:"failed",message:e,duration:n}:a))}},N=J({title:s("machines:team"),dataIndex:"teamName",key:"teamName",renderWrapper:t=>e.jsx(ft,{children:t})}),k=J({title:s("machines:bridge"),dataIndex:"bridgeName",key:"bridgeName",renderWrapper:t=>e.jsx(ft,{children:t})}),$=ee({title:s("machines:status"),dataIndex:"status",key:"status",width:140,statusMap:{pending:{color:"default",label:s("machines:pending"),icon:e.jsx(d,{})},testing:{color:"blue",label:s("machines:testing"),icon:e.jsx(H,{spin:!0})},success:{color:"success",label:s("machines:connected"),icon:e.jsx(u,{})},failed:{color:"error",label:s("machines:failed"),icon:e.jsx(Q,{})}}}),w=J({title:s("machines:message"),dataIndex:"message",key:"message",ellipsis:!0,renderText:e=>e||"-"}),C=[{title:s("machines:machineName"),dataIndex:"machineName",key:"machineName",render:(t,a)=>e.jsxs(gt,{"data-testid":`connectivity-machine-${t}`,children:[e.jsx(yt,{$variant:a.status,children:(()=>{switch(a.status){case"testing":return e.jsx(H,{spin:!0,"data-testid":`connectivity-status-icon-testing-${t}`});case"success":return e.jsx(u,{"data-testid":`connectivity-status-icon-success-${t}`});case"failed":return e.jsx(Q,{"data-testid":`connectivity-status-icon-failed-${t}`});default:return e.jsx(d,{"data-testid":`connectivity-status-icon-pending-${t}`})}})()}),e.jsx(xt,{children:t})]})},N,k,{...$,render:(t,a,i)=>e.jsx("span",{"data-testid":`connectivity-status-tag-${a.machineName}-${t}`,children:$.render?.(t,a,i)})},{title:s("machines:responseTime"),dataIndex:"duration",key:"duration",width:120,render:e=>e?e<1e3?`${e}ms`:`${(e/1e3).toFixed(1)}s`:"-"},{...w,render:(t,a,i)=>{if(!t)return w.render?.(t,a,i);const n=w.render?.(t,a,i);return e.jsx(bt,{$isError:"failed"===a.status,children:n})}}];return e.jsx(Ye,{"data-testid":"connectivity-modal",title:e.jsxs(tt,{children:[e.jsx(P,{}),s("machines:connectivityTest")]}),open:t,onCancel:i,className:m.ExtraLarge,destroyOnHidden:!0,footer:e.jsxs(at,{children:[e.jsx(it,{type:"primary",icon:e.jsx(H,{}),onClick:async()=>{l(!0);for(let a=0;a<n.length;a++)y(a),g(Math.round(a/n.length*100)),await v(n[a],a);g(100),l(!1),y(-1);const e=r.filter(e=>"success"===e.status).length,t=r.filter(e=>"failed"===e.status).length;0===t?h("success",s("machines:allMachinesConnected",{count:e})):h("warning",s("machines:machinesConnectedWithFailures",{successCount:e,failedCount:t}))},disabled:c||0===n.length,loading:c,"data-testid":"connectivity-run-test-button",children:s(c?"machines:testing":"machines:runTest")}),e.jsx(ue,{title:"Close",children:e.jsx(nt,{icon:e.jsx(Q,{}),onClick:i,"data-testid":"connectivity-close-button","aria-label":"Close"})})]}),children:e.jsx(Je,{children:e.jsxs(et,{children:[c&&e.jsxs(st,{"data-testid":"connectivity-progress-container",children:[e.jsx(rt,{percent:p,status:"active","data-testid":"connectivity-progress-bar"}),x>=0&&x<n.length&&e.jsx(ot,{"data-testid":"connectivity-progress-text",children:s("machines:testingMachine",{machineName:n[x].machineName})})]}),e.jsx(ct,{message:s("machines:connectivityTestDescription"),type:"info",showIcon:!0,icon:e.jsx(P,{}),"data-testid":"connectivity-info-alert"}),e.jsx(pt,{columns:C,dataSource:r,rowKey:"machineName",pagination:!1,scroll:{y:400},loading:0===n.length,rowClassName:e=>`status-${e.status}`,"data-testid":"connectivity-results-table"}),!c&&r.some(e=>"pending"!==e.status)&&e.jsx(lt,{"data-testid":"connectivity-summary-statistics",children:e.jsxs(mt,{children:[e.jsxs(dt,{"data-testid":"connectivity-total-machines",children:[e.jsxs(ut,{children:[s("machines:totalMachines"),":"]}),e.jsx(ht,{children:n.length})]}),e.jsxs(dt,{"data-testid":"connectivity-connected-count",children:[e.jsxs(ut,{children:[s("machines:connected"),":"]}),e.jsx(ht,{$variant:"success",children:r.filter(e=>"success"===e.status).length})]}),e.jsxs(dt,{"data-testid":"connectivity-failed-count",children:[e.jsxs(ut,{children:[s("machines:failed"),":"]}),e.jsx(ht,{$variant:"error",children:r.filter(e=>"failed"===e.status).length})]}),e.jsxs(dt,{"data-testid":"connectivity-average-response",children:[e.jsxs(ut,{children:[s("machines:averageResponse"),":"]}),e.jsx(ht,{children:(()=>{const e=r.filter(e=>"success"===e.status&&e.duration);if(0===e.length)return"-";const t=e.reduce((e,t)=>e+(t.duration||0),0)/e.length;return t<1e3?`${Math.round(t)}ms`:`${(t/1e3).toFixed(1)}s`})()})]})]})})]})})})},vt={team:{background:"var(--color-success)",color:"var(--color-text-inverse)"},bridge:{background:"var(--color-primary)",color:"var(--color-text-inverse)"},region:{background:"var(--color-info)",color:"var(--color-text-inverse)"},repository:{background:"var(--color-secondary)",color:"var(--color-text-inverse)"},status:{background:"var(--color-warning)",color:"var(--color-text-inverse)"},grand:{background:"var(--color-secondary)",color:"var(--color-text-inverse)"}},Nt=ae.div`
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
`,kt=ae.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
`,$t=ae.div`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
  padding: ${({theme:e})=>e.spacing.SM}px ${({theme:e})=>e.spacing.MD}px;
  background-color: var(--color-bg-secondary);
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border: 1px solid var(--color-border-secondary);
  gap: ${({theme:e})=>e.spacing.MD}px;
`,wt=ae.span`
  font-weight: 600;
  color: var(--color-text-primary);
`,Ct=ae.div`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
`,St=ae(ce)`
  && {
    min-width: 42px;
    height: ${p.DIMENSIONS.CONTROL_HEIGHT_SM}px;
    border-radius: ${({theme:e})=>e.borderRadius.SM}px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
`,Mt=ae.span`
  width: 1px;
  height: 24px;
  background-color: var(--color-border-secondary);
  margin: 0 ${({theme:e})=>e.spacing.SM}px;
`,It=ae(he).attrs({image:he.PRESENTED_IMAGE_SIMPLE})`
  margin-top: ${({theme:e})=>e.spacing.XL}px;
`,Tt=ae.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XL}px;
`,Rt=ae(pe)`
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
`,At=ae.div`
  display: flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
  padding: ${({theme:e})=>e.spacing.XS}px 0;
`,Et=ae.div`
  width: 4px;
  height: ${p.DIMENSIONS.ICON_XL}px;
  border-radius: ${({theme:e})=>e.borderRadius.SM}px;
  background-color: ${({$color:e})=>e||"var(--color-text-secondary)"};
`,Dt=ae.span`
  font-size: 18px;
  font-weight: 700;
  color: var(--color-text-primary);
`,Vt=ae.span`
  font-size: 14px;
  color: var(--color-text-secondary);
`,Ft=ae.div`
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
`,Ot=ae.div`
  display: flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.LG}px;
`,Pt=ae(g)`
  font-size: ${p.DIMENSIONS.ICON_MD}px;
  color: var(--color-primary);
`,zt=ae(Pt)`
  font-size: ${p.DIMENSIONS.ICON_LG}px;
`,Lt=ae.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XS}px;
`,Gt=ae.span`
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
`,_t=ae(ce)`
  && {
    /* Maintain compact pill styling to mirror historical control surface */
    height: ${p.DIMENSIONS.CONTROL_HEIGHT_SM}px;
    border-radius: ${({theme:e})=>e.borderRadius.SM}px;
    display: inline-flex;
    align-items: center;
    gap: ${({theme:e})=>e.spacing.XS}px;
  }
`,Bt=ae.span`
  font-size: 18px;
  color: ${({$status:e})=>{switch(e){case"online":return"var(--color-success)";case"offline":return"var(--color-text-tertiary)";default:return"var(--color-text-quaternary)"}}};
  display: inline-flex;
  align-items: center;
  justify-content: center;
`,Wt=ae(de)`
  && {
    border: none;
    border-radius: ${({theme:e})=>e.borderRadius.MD}px;
    font-weight: 500;
    display: inline-flex;
    align-items: center;
    gap: ${({theme:e})=>e.spacing.XS}px;
    padding: 0 ${({theme:e})=>e.spacing.SM}px;
    line-height: 24px;
    background-color: ${({$variant:e})=>vt[e].background};
    color: ${({$variant:e})=>vt[e].color};
  }
`,Ht=ae(Wt)`
  && {
    font-size: 16px;
    padding: 4px ${({theme:e})=>e.spacing.MD}px;
  }
`,Qt=ae(ge)`
  && .ant-badge-count {
    background-color: ${({$isPositive:e})=>e?"var(--color-success)":"var(--color-border-secondary)"};
    color: ${({$isPositive:e})=>e?"var(--color-text-inverse)":"var(--color-text-secondary)"};
  }
`,Xt=({teamFilter:s,showActions:r=!0,className:o="",onEditMachine:c,onFunctionsMachine:l,onDeleteMachine:m,enabled:d=!0,onQueueItemCreated:w,onRowClick:C,selectedMachine:S})=>{const{t:M}=fe(["machines","common","functions","resources"]),I=i(),T=t(e=>e.ui.uiMode),R="expert"===T,{executePingForMachineAndWait:A}=Ue(),E=a.useRef(null),[D,V]=a.useState("machine"),[F,O]=a.useState([]),L=f(),G=b(),W=b(),[H,Q]=a.useState(!1),[X,q]=a.useState(!1),[U,K]=a.useState(!1),[Z,ee]=a.useState(null),[ae,ie]=a.useState(!1);n.useEffect(()=>{"simple"===T&&"machine"!==D&&V("machine")},[T,D]);const{data:se=[],isLoading:re,refetch:le}=ve(s,d),{data:me=[]}=Ne(s),de=((e,t={})=>{const{rowHeight:i=54,headerHeight:n=55,paginationHeight:s=64,containerOffset:r=32,minRows:o=5,maxRows:c=100}=t,[l,m]=a.useState(10),d=a.useRef(null),u=a.useCallback(()=>{if(!e.current)return;const t=e.current.offsetHeight-n-s-r,a=Math.floor(t/i),l=Math.max(o,Math.min(c,a));m(l)},[e,i,n,s,r,o,c]),h=a.useRef(null);return a.useEffect(()=>(h.current=ne.debounce(u,300),()=>{h.current?.cancel()}),[u]),a.useEffect(()=>(u(),e.current&&window.ResizeObserver&&(d.current=new ResizeObserver(()=>{h.current?.()}),d.current.observe(e.current)),()=>{d.current&&d.current.disconnect(),h.current?.cancel()}),[u,e]),l})(E,{containerOffset:170,minRows:5,maxRows:50}),he=se,pe=e=>Fe(e,me.map(e=>({repositoryGuid:e.repositoryGuid,repositoryName:e.repositoryName,grandGuid:e.grandGuid}))),ge=a.useCallback(e=>{m&&m(e)},[m]),ye=a.useCallback(e=>{C?C(e):(ee(e),ie(!0))},[C]),ke=a.useCallback(()=>{ie(!1),ee(null)},[]),{getFunctionsByCategory:$e}=z(),we=a.useMemo(()=>$e("machine").filter(e=>e&&!1!==e.showInMenu&&"mount"!==e.name&&"pull"!==e.name),[$e]),Ce=R&&j.isEnabled("assignToCluster"),Se=a.useCallback(e=>{e.open&&e.machine?W.open(e.machine):W.close()},[W]),Te=a.useCallback(e=>{e.open&&e.entityType&&e.entityIdentifier?L.open({entityType:e.entityType,entityIdentifier:e.entityIdentifier,entityName:e.entityName}):L.close()},[L]),Re=n.useMemo(()=>(({t:t,isExpertMode:a,uiMode:i,showActions:n,hasSplitView:s,canAssignToCluster:r,onEditMachine:o,onFunctionsMachine:c,handleDelete:l,handleRowClick:m,executePingForMachineAndWait:d,setAssignClusterModal:g,setAuditTraceModal:f,machineFunctions:b})=>{const j=[],v=J({title:t("machines:machineName"),dataIndex:"machineName",key:"machineName",sorter:Oe("machineName"),renderWrapper:t=>e.jsxs(oe,{children:[e.jsx(Pt,{}),e.jsx("strong",{children:t})]})});return j.push({title:t("machines:status"),dataIndex:"vaultStatusTime",key:"status",width:100,align:"center",sorter:Pe(e=>{if(!e.vaultStatusTime)return 1/0;const t=new Date(e.vaultStatusTime+"Z");return((new Date).getTime()-t.getTime())/6e4<=3?0:1}),render:(a,i)=>{if(!i.vaultStatusTime)return e.jsx(ue,{title:t("machines:statusUnknown"),children:e.jsx(Bt,{$status:"unknown",children:e.jsx(ze,{})})});const n=new Date(i.vaultStatusTime+"Z"),s=((new Date).getTime()-n.getTime())/6e4<=3;return e.jsx(ue,{title:t(s?"machines:connected":"machines:connectionFailed"),children:e.jsx(Bt,{$status:s?"online":"offline",children:s?e.jsx(u,{}):e.jsx(ze,{})})})}},v),s||j.push(J({title:t("machines:team"),dataIndex:"teamName",key:"teamName",width:150,sorter:Oe("teamName"),renderWrapper:t=>e.jsx(Wt,{$variant:"team",children:t})})),s||(a?j.push(J({title:t("machines:region"),dataIndex:"regionName",key:"regionName",width:150,sorter:Oe("regionName"),renderText:e=>e||"-",renderWrapper:(t,a)=>"-"===a?e.jsx("span",{children:"-"}):e.jsx(Wt,{$variant:"region",children:t})}),J({title:t("machines:bridge"),dataIndex:"bridgeName",key:"bridgeName",width:150,sorter:Oe("bridgeName"),renderWrapper:t=>e.jsx(Wt,{$variant:"bridge",children:t})})):"simple"!==i&&j.push(J({title:t("bridges.bridge"),dataIndex:"bridgeName",key:"bridgeName",width:150,sorter:Oe("bridgeName"),renderWrapper:t=>e.jsx(Wt,{$variant:"bridge",children:t})}))),!s&&r&&j.push({title:t("machines:assignmentStatus.title"),key:"assignmentStatus",width:180,ellipsis:!0,render:(t,a)=>e.jsx(Ae,{machine:a})}),s||j.push({title:t("machines:queueItems"),dataIndex:"queueCount",key:"queueCount",width:100,align:"center",sorter:Oe("queueCount"),render:t=>e.jsx(Qt,{$isPositive:t>0,count:t,showZero:!0})}),n&&j.push(te({title:t("common:table.actions"),width:p.DIMENSIONS.CARD_WIDTH,renderActions:a=>e.jsx(_e,{buttons:[{type:"view",icon:e.jsx(Le,{}),tooltip:"common:viewDetails",onClick:()=>m(a),variant:"default",testIdSuffix:"view-details"},{type:"edit",icon:e.jsx(He,{}),tooltip:"common:actions.edit",onClick:()=>o?.(a)},{type:"remote",icon:e.jsx(Qe,{}),tooltip:"machines:remote",dropdownItems:[{key:"functions",label:t("machines:runAction"),icon:e.jsx(Qe,{}),children:[...b.filter(e=>!1!==e?.showInMenu).map(t=>({key:`function-${t?.name||"unknown"}`,label:e.jsx("span",{title:t?.description||"",children:t?.name||"Unknown"}),onClick:()=>c?.(a,t?.name)})),{type:"divider"},{key:"advanced",label:t("machines:advanced"),icon:e.jsx(Qe,{}),onClick:()=>c?.(a)}]},{key:"test",label:t("machines:connectivityTest"),icon:e.jsx(P,{}),onClick:async()=>{h("info",t("machines:testingConnection"));const e=await d(a,{priority:4,description:"Connectivity test",addedVia:"machine-table",timeout:15e3});e.success?h("success",t("machines:connectionSuccessful")):h("error",e.error||t("machines:connectionFailed"))}},...r?[{key:"assignCluster",label:a.distributedStorageClusterName?t("machines:changeClusterAssignment"):t("machines:assignToCluster"),icon:e.jsx(be,{}),onClick:()=>g({open:!0,machine:a})}]:[]]},{type:"trace",icon:e.jsx(x,{}),tooltip:"machines:trace",onClick:()=>f({open:!0,entityType:"Machine",entityIdentifier:a.machineName,entityName:a.machineName})},{type:"delete",icon:e.jsx(y,{}),tooltip:"common:actions.delete",onClick:()=>l(a),danger:!0},{type:"custom",render:t=>e.jsx(Ge,{machine:t.machineName,teamName:t.teamName})}],record:a,idField:"machineName",testIdPrefix:"machine",t:t})})),j})({t:M,isExpertMode:R,uiMode:T,showActions:r,hasSplitView:Boolean(C),canAssignToCluster:Ce,onEditMachine:c,onFunctionsMachine:l,handleDelete:ge,handleRowClick:ye,executePingForMachineAndWait:A,setAssignClusterModal:Se,setAuditTraceModal:Te,machineFunctions:we}),[M,R,T,r,C,Ce,c,l,ge,ye,A,Se,Te,we]),Be=Ce?{selectedRowKeys:F,onChange:e=>{O(e)},getCheckboxProps:e=>({disabled:!1,"data-testid":`machine-checkbox-${e.machineName}`})}:void 0,We=a.useMemo(()=>{const e={};return"machine"===D||he.forEach(t=>{let a="";if("bridge"===D)a=t.bridgeName;else if("team"===D)a=t.teamName;else if("region"===D)a=t.regionName||"Unknown";else{if("repository"===D){const a=pe(t);if(0===a.length)return;return void a.forEach(a=>{const i=a.name;e[i]||(e[i]=[]),e[i].find(e=>e.machineName===t.machineName)||e[i].push(t)})}if("status"===D){const e=pe(t);if(0===e.length)a="No Repositories";else{const t=e.some(e=>!e.accessible),i=e.some(e=>e.mounted&&e.docker_running),n=e.some(e=>e.mounted&&!e.docker_running),s=e.some(e=>!e.mounted);a=t?"Inaccessible":i?"Active (Running)":n?"Ready (Stopped)":s?"Not Mounted":"Unknown Status"}}else if("grand"===D){const a=pe(t);if(0===a.length)return;return void a.forEach(a=>{let i="No Grand Repository";if(a.grandGuid){const e=me.find(e=>e.repositoryGuid===a.grandGuid);e&&(i=e.repositoryName)}e[i]||(e[i]=[]),e[i].find(e=>e.machineName===t.machineName)||e[i].push(t)})}}a&&(e[a]||(e[a]=[]),e[a].push(t))}),e},[he,D,me,pe]);return e.jsxs(Nt,{className:o,children:["simple"===T?null:e.jsx(Ct,{children:e.jsxs(oe,{wrap:!0,size:"small",children:[e.jsx(ue,{title:M("machines:machine"),children:e.jsx(St,{type:"machine"===D?"primary":"default",icon:e.jsx(g,{}),onClick:()=>V("machine"),"data-testid":"machine-view-toggle-machine","aria-label":M("machines:machine")})}),e.jsx(Mt,{}),e.jsx(ue,{title:M("machines:groupByBridge"),children:e.jsx(St,{type:"bridge"===D?"primary":"default",icon:e.jsx(be,{}),onClick:()=>V("bridge"),"data-testid":"machine-view-toggle-bridge","aria-label":M("machines:groupByBridge")})}),e.jsx(ue,{title:M("machines:groupByTeam"),children:e.jsx(St,{type:"team"===D?"primary":"default",icon:e.jsx(v,{}),onClick:()=>V("team"),"data-testid":"machine-view-toggle-team","aria-label":M("machines:groupByTeam")})}),R&&e.jsx(ue,{title:M("machines:groupByRegion"),children:e.jsx(St,{type:"region"===D?"primary":"default",icon:e.jsx(N,{}),onClick:()=>V("region"),"data-testid":"machine-view-toggle-region","aria-label":M("machines:groupByRegion")})}),e.jsx(ue,{title:M("machines:groupByRepository"),children:e.jsx(St,{type:"repository"===D?"primary":"default",icon:e.jsx(k,{}),onClick:()=>V("repository"),"data-testid":"machine-view-toggle-repository","aria-label":M("machines:groupByRepository")})}),e.jsx(ue,{title:M("machines:groupByStatus"),children:e.jsx(St,{type:"status"===D?"primary":"default",icon:e.jsx(_,{}),onClick:()=>V("status"),"data-testid":"machine-view-toggle-status","aria-label":M("machines:groupByStatus")})}),e.jsx(ue,{title:M("machines:groupByGrand"),children:e.jsx(St,{type:"grand"===D?"primary":"default",icon:e.jsx(je,{}),onClick:()=>V("grand"),"data-testid":"machine-view-toggle-grand","aria-label":M("machines:groupByGrand")})})]})}),Ce&&0!==F.length?e.jsxs($t,{children:[e.jsxs(oe,{size:"middle",children:[e.jsx(wt,{children:M("machines:bulkActions.selected",{count:F.length})}),e.jsx(ue,{title:M("common:actions.clearSelection"),children:e.jsx(ce,{size:"small",onClick:()=>O([]),"data-testid":"machine-bulk-clear-selection","aria-label":M("common:actions.clearSelection")})})]}),e.jsxs(oe,{size:"middle",children:[e.jsx(ue,{title:M("machines:bulkActions.assignToCluster"),children:e.jsx(ce,{type:"primary",icon:e.jsx(be,{}),onClick:()=>Q(!0),"data-testid":"machine-bulk-assign-cluster","aria-label":M("machines:bulkActions.assignToCluster")})}),e.jsx(ue,{title:M("machines:bulkActions.removeFromCluster"),children:e.jsx(ce,{icon:e.jsx(be,{}),onClick:()=>q(!0),"data-testid":"machine-bulk-remove-cluster","aria-label":M("machines:bulkActions.removeFromCluster")})}),e.jsx(ue,{title:M("machines:bulkActions.viewAssignmentStatus"),children:e.jsx(ce,{icon:e.jsx($,{}),onClick:()=>K(!0),"data-testid":"machine-bulk-view-status","aria-label":M("machines:bulkActions.viewAssignmentStatus")})})]})]}):null,"machine"===D?e.jsx(kt,{ref:E,children:e.jsx(xe,{columns:Re,dataSource:he,rowKey:"machineName",loading:re,scroll:{x:"max-content"},rowSelection:Be,rowClassName:e=>{const t="machine-table-row";return S?.machineName===e.machineName?`${t} machine-table-row--selected`:t},"data-testid":"machine-table",pagination:{pageSize:de,showSizeChanger:!1,showTotal:(e,t)=>M("common:table.showingRecords",{start:t[0],end:t[1],total:e})},onRow:e=>({"data-testid":`machine-row-${e.machineName}`,onClick:t=>{const a=t.target;a.closest("button")||a.closest(".ant-dropdown")||a.closest(".ant-dropdown-menu")||I(`/machines/${e.machineName}/repositories`,{state:{machine:e}})}}),sticky:!0})}):(()=>{if(0===Object.keys(We).length)return e.jsx(It,{description:M("resources:repositories.noRepositories")});const t={machine:"repository",bridge:"bridge",team:"team",region:"region",repository:"repository",status:"status",grand:"grand"},a={team:"var(--color-success)",bridge:"var(--color-primary)",region:"var(--color-info)",repository:"var(--color-secondary)",status:"var(--color-warning)",grand:"var(--color-secondary)"},i={bridge:e.jsx(be,{}),team:e.jsx(v,{}),region:e.jsx(N,{}),repository:e.jsx(k,{}),status:e.jsx(_,{}),grand:e.jsx(je,{})};return e.jsx(Tt,{children:Object.entries(We).map(([n,s],r)=>{const o=t[D],c=a[o];return e.jsxs(Rt,{$isAlternate:r%2==0,children:[e.jsxs(At,{children:[e.jsx(Et,{$color:c}),e.jsxs(oe,{size:"small",children:[e.jsxs(Dt,{children:["#",r+1]}),e.jsx(Ht,{$variant:o,icon:i[D],children:n}),e.jsxs(Vt,{children:[s.length," ",1===s.length?M("machines:machine"):M("machines:machines")]})]})]}),s.map((t,a)=>e.jsxs(Ft,{$isStriped:a%2!=0,onClick:()=>I(`/machines/${t.machineName}/repositories`,{state:{machine:t}}),"data-testid":`grouped-machine-row-${t.machineName}`,children:[e.jsxs(Ot,{children:[e.jsx(zt,{}),e.jsxs(Lt,{children:[e.jsx(Gt,{children:t.machineName}),e.jsxs(oe,{size:"small",children:[e.jsx(Wt,{$variant:"team",children:t.teamName}),t.bridgeName&&e.jsx(Wt,{$variant:"bridge",children:t.bridgeName}),t.regionName&&e.jsx(Wt,{$variant:"region",children:t.regionName})]})]})]}),e.jsx(ue,{title:M("machines:viewRepositories"),children:e.jsx(_t,{type:"primary",icon:e.jsx(B,{}),onClick:e=>{e.stopPropagation(),I(`/machines/${t.machineName}/repositories`,{state:{machine:t}})},children:M("machines:viewRepositories")})})]},t.machineName))]},n)})})})(),e.jsx(Me,{open:L.isOpen,onCancel:L.close,entityType:L.entityType,entityIdentifier:L.entityIdentifier,entityName:L.entityName}),G.state.data&&e.jsx(Y,{open:G.isOpen,onCancel:G.close,machineName:G.state.data.machineName,teamName:G.state.data.teamName,bridgeName:G.state.data.bridgeName,onQueueItemCreated:w}),W.state.data&&e.jsx(Ee,{open:W.isOpen,machine:W.state.data,onCancel:W.close,onSuccess:()=>{W.close(),le()}}),e.jsx(Ee,{open:H,machines:se.filter(e=>F.includes(e.machineName)),onCancel:()=>Q(!1),onSuccess:()=>{Q(!1),O([]),le()}}),e.jsx(De,{open:X,machines:se.filter(e=>F.includes(e.machineName)),onCancel:()=>q(!1),onSuccess:()=>{q(!1),O([]),le()}}),e.jsx(Ve,{open:U,machines:se.filter(e=>F.includes(e.machineName)),onCancel:()=>K(!1)}),!C&&e.jsx(Ie,{machine:Z,visible:ae,onClose:ke})]})},qt=ae.div`
  display: flex;
  height: 100%;
  width: 100%;
  position: relative;
  overflow: hidden;
`,Ut=ae.div`
  width: ${({$width:e})=>e};
  height: 100%;
  overflow: auto;
  min-width: 300px;
  transition: width 0.3s ease-in-out;
`,Kt=ae.div`
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
`,Zt=t=>{const{type:i,selectedResource:n,onResourceSelect:s,isPanelCollapsed:r=!0,onTogglePanelCollapse:o}=t,c=Te(),[l,m]=a.useState(c),[d,u]=a.useState(!1),[h,p]=a.useState(!1);a.useEffect(()=>{m(c)},[c]),a.useEffect(()=>{if(!n){u(!1);const e=setTimeout(()=>{p(!1)},250);return()=>clearTimeout(e)}p(!0),requestAnimationFrame(()=>{u(!0)})},[n]);const g=e=>{s(e)},x=()=>{s(null)},y=r?50:l;if("machine"===i){const a=n?`calc(100% - ${y}px)`:"100%";return e.jsxs(qt,{"data-testid":"split-resource-view-container",children:[e.jsx(Ut,{$width:a,"data-testid":"split-resource-view-left-panel",children:e.jsx(Xt,{...t,onRowClick:g,selectedMachine:n})}),h&&e.jsx(Kt,{$visible:d,$rightOffset:y,onClick:x,"data-testid":"split-resource-view-backdrop"}),n&&e.jsx(Re,{type:"machineName"in n?"machine":"repositoryName"in n?"repository":"container",data:n,visible:!0,onClose:x,splitWidth:l,onSplitWidthChange:m,isCollapsed:r,onToggleCollapse:o,collapsedWidth:50})]})}return null},Yt=()=>{const{t:t}=fe(["resources","machines","common"]),[n,r]=ye.useModal(),o=s(),c=i(),l=se(),{teams:m,selectedTeams:d,setSelectedTeams:u,isLoading:p}=Be(),{modalState:g,currentResource:x,openModal:y,closeModal:f}=Xe("machine"),[j,v]=a.useState(null),[N,k]=a.useState(null),[$,O]=a.useState(null),[z,_]=a.useState(!0),[B,H]=a.useState({}),{state:Q,open:X,close:q}=w(),K=b(),{data:Z=[],refetch:Y}=ve(d.length>0?d:void 0,d.length>0),{data:J=[]}=Ne(d.length>0?d:void 0),{data:ee=[]}=L(d.length>0?d:void 0),te=ke(),ae=$e(),ie=we(),ne=Ce(),re=Se(),{executeAction:oe,isExecuting:ce}=U();a.useEffect(()=>{const e=o.state;e?.createRepository&&c("/credentials",{state:e,replace:!0})},[o,c]);const le=e=>{v(e),e&&(k(null),O(null),_(!1))},me=a.useCallback(e=>{qe({modal:n,t:t,resourceType:"machine",resourceName:e.machineName,translationNamespace:"machines",onConfirm:()=>ne.mutateAsync({teamName:e.teamName,machineName:e.machineName}),onSuccess:()=>Y()})},[ne,n,Y,t]),de=a.useCallback(async e=>{try{if("create"===g.mode){const{autoSetup:i,...n}=e;if(await te.mutateAsync(n),h("success",t("machines:createSuccess")),i)try{await new Promise(e=>setTimeout(e,500));const a=await oe({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,functionName:"setup",params:{datastore_size:"95%",source:"apt-repo",rclone_source:"install-script",docker_source:"docker-repo",install_amd_driver:"auto",install_nvidia_driver:"auto"},priority:3,description:`Auto-setup for machine ${e.machineName}`,addedVia:"machine-creation-auto-setup",machineVault:e.machineVault||"{}"});a.success&&(a.taskId?(h("info",t("machines:setupQueued")),X(a.taskId,e.machineName)):a.isQueued&&h("info",t("machines:setupQueuedForSubmission")))}catch(a){h("warning",t("machines:machineCreatedButSetupFailed"))}f(),Y()}else if(x){const t=x.machineName,a=e.machineName;a&&a!==t&&await ae.mutateAsync({teamName:x.teamName,currentMachineName:t,newMachineName:a}),e.bridgeName&&e.bridgeName!==x.bridgeName&&await ie.mutateAsync({teamName:x.teamName,machineName:a||t,newBridgeName:e.bridgeName});const i=e.machineVault;i&&i!==x.vaultContent&&await re.mutateAsync({teamName:x.teamName,machineName:a||t,machineVault:i,vaultVersion:x.vaultVersion+1}),f(),Y()}}catch(a){}},[f,te,x,oe,X,Y,t,g.mode,ie,ae,re]),pe=a.useCallback(async(e,t)=>{if(x)try{await re.mutateAsync({teamName:x.teamName,machineName:x.machineName,machineVault:e,vaultVersion:t}),f(),Y()}catch(a){}},[f,x,Y,re]),ge=a.useCallback(async e=>{if(x)try{const a=x.machineName,i=x.bridgeName,n=m.find(e=>e.teamName===x.teamName),s={teamName:x.teamName,machineName:a,bridgeName:i,functionName:e.function.name,params:e.params,priority:e.priority,description:e.description,addedVia:"machine-table",teamVault:n?.vaultContent||"{}",machineVault:x.vaultContent||"{}"};if(e.params.repo){const t=J.find(t=>t.repositoryGuid===e.params.repo);s.repositoryGuid=t?.repositoryGuid||e.params.repo,s.repositoryVault=t?.vaultContent||"{}"}else s.repositoryVault="{}";if("pull"===e.function.name){if("machine"===e.params.sourceType&&e.params.from){const t=Z.find(t=>t.machineName===e.params.from);t?.vaultContent&&(s.sourceMachineVault=t.vaultContent)}if("storage"===e.params.sourceType&&e.params.from){const t=ee.find(t=>t.storageName===e.params.from);t?.vaultContent&&(s.sourceStorageVault=t.vaultContent)}}const r=await oe(s);f(),r.success?r.taskId?(h("success",t("machines:queueItemCreated")),X(r.taskId,a)):r.isQueued&&h("info",t("resources:messages.highestPriorityQueued",{resourceType:"machine"})):h("error",r.error||t("resources:errors.failedToCreateQueueItem"))}catch(a){h("error",t("resources:errors.failedToCreateQueueItem"))}},[f,x,oe,Z,X,J,ee,t,m]),xe=te.isPending||ae.isPending||ie.isPending||ce,be=re.isPending;return e.jsxs(e.Fragment,{children:[e.jsx(C,{children:e.jsxs(S,{children:[e.jsx(M,{children:e.jsxs(I,{children:[e.jsx(T,{children:e.jsx(R,{children:e.jsx(We,{"data-testid":"machines-team-selector",teams:m,selectedTeams:d,onChange:u,loading:p,placeholder:t("teams.selectTeamToView"),style:{width:"100%"}})})}),d.length>0&&e.jsxs(A,{children:[e.jsx(ue,{title:t("machines:createMachine"),children:e.jsx(E,{type:"primary",icon:e.jsx(D,{}),"data-testid":"machines-create-machine-button",onClick:()=>y("create"),"aria-label":t("machines:createMachine")})}),e.jsx(ue,{title:t("machines:connectivityTest"),children:e.jsx(E,{icon:e.jsx(P,{}),"data-testid":"machines-connectivity-test-button",onClick:()=>K.open(),disabled:0===Z.length,"aria-label":t("machines:connectivityTest")})}),e.jsx(ue,{title:t("common:actions.refresh"),children:e.jsx(E,{icon:e.jsx(F,{}),"data-testid":"machines-refresh-button",onClick:()=>{Y(),H(e=>({...e,_global:Date.now()}))},"aria-label":t("common:actions.refresh")})})]})]})}),e.jsx(V,{children:0===d.length?e.jsx(he,{image:he.PRESENTED_IMAGE_SIMPLE,description:t("teams.selectTeamPrompt"),style:{padding:`${l.spacing.LG}px 0`}}):e.jsx(Zt,{type:"machine",teamFilter:d,showFilters:!0,showActions:!0,onCreateMachine:()=>y("create"),onEditMachine:e=>y("edit",e),onVaultMachine:e=>y("vault",e),onFunctionsMachine:(e,t)=>{y("create",e,t),H(t=>({...t,[e.machineName]:Date.now()}))},onDeleteMachine:me,enabled:d.length>0,refreshKeys:B,onQueueItemCreated:(e,t)=>{X(e,t)},selectedResource:j||N||$,onResourceSelect:e=>{e&&"machineName"in e?le(e):e&&"repositoryName"in e?(le(null),k(e),O(null),_(!1)):e&&"id"in e&&"state"in e?(le(null),k(null),O(e),_(!1)):(le(null),k(null),O(null))},isPanelCollapsed:z,onTogglePanelCollapse:()=>{_(e=>!e)}})})]})}),e.jsx(G,{"data-testid":"machines-machine-modal",open:g.open,onCancel:f,resourceType:"machine",mode:g.mode,existingData:g.data||x,teamFilter:d.length>0?d:void 0,preselectedFunction:g.preselectedFunction,onSubmit:de,onUpdateVault:"edit"===g.mode?pe:void 0,onFunctionSubmit:ge,isSubmitting:xe,isUpdatingVault:be,functionCategories:["machine","backup"],hiddenParams:[],defaultParams:{}}),e.jsx(W,{"data-testid":"machines-queue-trace-modal",taskId:Q.taskId,open:Q.open,onCancel:()=>{const e=Q.machineName;q(),e&&H(t=>({...t,[e]:Date.now()})),Y()}}),e.jsx(jt,{"data-testid":"machines-connectivity-test-modal",open:K.isOpen,onClose:K.close,machines:Z,teamFilter:d}),r]})};export{Yt as default};
