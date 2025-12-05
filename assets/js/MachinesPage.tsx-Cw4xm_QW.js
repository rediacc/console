import{j as e,u as t}from"./chunk-DUi8bg1D.js";import{b as a,h as n,R as i,u as s}from"./chunk-DDwtzQW6.js";import{d as r,m as o,B as c,M as l,h as m,i as d,j as u,k as h,l as p,o as g,e as x,b as f,s as y,p as b,D as j,C as v,H as N,q as k,t as w,w as $,x as C,T as S,G as M,I,y as T,g as R,R as A,n as E,z as V,P as D,A as F,F as O,J as P,K as L,N as z,O as G,Q as _,U as B,V as W,X as Q,Y as H}from"../index-DldRJJRQ.js";import{R as X}from"./chunk-143Yqtwm.js";import{u as q,W as U}from"./chunk-DoFHaoUB.js";import{u as K,a as Z,F as Y,U as J}from"./chunk-PcvFhBrK.js";import{Q as ee}from"./chunk-C0pO_7aD.js";import{S as te}from"./chunk-DTHX06Z8.js";import{C as ae}from"./chunk-Dv8HU_HO.js";import{u as ne}from"./chunk-Jyx4Lx9k.js";import{u as ie,A as se,a as re}from"./chunk-Cr6aYJuL.js";import{u as oe}from"./chunk-Bqnq7YJr.js";import{w as ce,R as le}from"./chunk-x9kHZLO3.js";import{c as me,a as de,b as ue}from"./chunk-wiPeo6cG.js";import{T as he,S as pe,c as ge,P as xe,A as fe,d as ye,s as be,E as je,C as ve,B as Ne,F as ke,M as we}from"./chunk-CX_EivFx.js";import{u as $e}from"./chunk-BQNjmpVv.js";import{B as Ce}from"./chunk-DwsVAQPO.js";import{u as Se,a as Me,b as Ie,c as Te,d as Re,e as Ae,f as Ee}from"./chunk-CKLjbfNQ.js";import{A as Ve}from"./chunk-BqB1pKeX.js";import{M as De,u as Fe,D as Oe,U as Pe}from"./chunk-Cu0qh_sP.js";import{M as Le,A as ze,R as Ge,V as _e}from"./chunk-Ddg9bahU.js";import"./chunk-BdxPdFN0.js";import{g as Be}from"./chunk-D1YgjPjx.js";import{c as We,a as Qe}from"./chunk-BKxNWyZX.js";import{D as He,E as Xe,L as qe}from"./chunk-kTJcUGxe.js";import{E as Ue}from"./chunk-DzCZ8c5k.js";import{F as Ke}from"./chunk-rMI0AfHI.js";import{u as Ze}from"./chunk-Bx5UP20U.js";import{u as Ye,T as Je}from"./chunk-ByFygCtT.js";import{c as et}from"./chunk-DTiGE0EW.js";import"./chunk-DB6ez0TU.js";import"./chunk-CqfAHVCa.js";import"./chunk-DDaRaurs.js";import"./chunk-DO7SKw9g.js";import"./chunk-Br9cBLjd.js";import"./chunk-B8PN3w5Q.js";import"./chunk-CY4jNBZn.js";import"./chunk-CersrgO7.js";import"./chunk-Dc77jU8D.js";import"./chunk-GYFfhnqx.js";import"./chunk-jsohsww4.js";import"./chunk-BqoklQRZ.js";import"./chunk-wbuWZ0uz.js";import"./chunk-CNJGz90N.js";import"./chunk-BveedPc4.js";import"./chunk-DlialLHl.js";import"./chunk-DhpoEw86.js";import"./chunk-BjQFYg8e.js";import"./chunk-YmwFJhnh.js";import"./chunk-Bd1yHLf3.js";import"./forkTokenService.ts-Cq2kqbJo.js";import"./chunk-DEO1aopL.js";function tt(e){const{buildQueueVault:t}=q();ie();const n=ne(),{data:i}=oe(),s=a.useCallback(async e=>{try{const a=function(e,t){if(e.teamVault&&"{}"!==e.teamVault)return e.teamVault;const a=t?.find(t=>t.teamName===e.teamName);return a?.vaultContent||"{}"}(e,i),s=await async function(e,t,a){const n=4,i="ping-service",s="{}";return a({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,functionName:"ping",params:{},priority:e.priority||n,addedVia:e.addedVia||i,machineVault:e.machineVault||s,teamVault:t,repoVault:e.repoVault||s})}(e,a,t),r=await async function(e,t,a){const n=4,i=await a.mutateAsync({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,queueVault:t,priority:e.priority||n});return s=i,(e=>{if("object"!=typeof e||null===e)return!1;const t=e,a=void 0===t.taskId||"string"==typeof t.taskId,n=void 0===t.isQueued||"boolean"==typeof t.isQueued;return a&&n})(s)?s:{};var s}(e,s,n);return{taskId:r?.taskId,success:!!r?.taskId||!!r?.isQueued}}catch(a){return{success:!1,error:a instanceof Error?a.message:"Failed to execute ping function"}}},[t,n,i]),r=a.useCallback(async(e,t)=>s({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,priority:t?.priority,description:t?.description,addedVia:t?.addedVia,machineVault:e.vaultContent||"{}"}),[s]),o=a.useCallback(async(e,t)=>{const a=await s(e);if(!a.success||!a.taskId)return a;const n=await ce(a.taskId,t);return{...a,completionResult:n,success:n.success,error:n.success?void 0:n.message}},[s]),c=a.useCallback(async(e,t)=>o({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,priority:t?.priority,description:t?.description,addedVia:t?.addedVia,machineVault:e.vaultContent||"{}"},t?.timeout),[o]);return{executePing:s,executePingForMachine:r,executePingAndWait:o,executePingForMachineAndWait:c,waitForQueueItemCompletion:ce,isLoading:n.isPending}}const{Text:at}=he,nt=o`
  0% {
    opacity: 0.65;
  }
  50% {
    opacity: 1;
  }
  100% {
    opacity: 0.65;
  }
`,it=r(c)`
  .ant-modal-body {
    padding: ${({theme:e})=>e.spacing.XL}px;
  }
`,st=r(l)`
  width: 100%;
`,rt=r(m)``,ot=r(pe)`
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
`,ct=r(d)``,lt=r(u)`
  && {
    min-width: ${({theme:e})=>2*e.spacing.XXL}px;
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,mt=r(ge)`
  && {
    min-width: ${({theme:e})=>e.dimensions.CONTROL_HEIGHT}px;
    min-height: ${({theme:e})=>e.dimensions.CONTROL_HEIGHT}px;
    border-radius: ${({theme:e})=>e.borderRadius.LG}px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,dt=r.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XS}px;
`,ut=r(xe)`
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
`,ht=r(at)`
  && {
    font-size: ${({theme:e})=>e.fontSize.XS}px;
    color: ${({theme:e})=>e.colors.textSecondary};
  }
`,pt=r(fe)`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.LG}px;
    font-size: ${({theme:e})=>e.fontSize.SM}px;
  }
`,gt=r.div`
  padding: ${({theme:e})=>e.spacing.MD}px;
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
  background-color: ${({theme:e})=>e.colors.bgSecondary};
`,xt=r.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({theme:e})=>e.spacing.XL}px;
`,ft=r.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XS}px;
`,yt=r(at)`
  && {
    color: ${({theme:e})=>e.colors.textSecondary};
  }
`,bt=r(at)`
  && {
    color: ${({theme:e,$variant:t})=>"success"===t?e.colors.success:"error"===t?e.colors.error:e.colors.textPrimary};
    font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
  }
`,jt=r(h)`
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
`,vt=r.div`
  display: inline-flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,Nt=r(at)`
  && {
    font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
  }
`,kt=r.span`
  display: inline-flex;
  align-items: center;
  color: ${({theme:e,$variant:t})=>{switch(t){case"success":return e.colors.success;case"failed":return e.colors.error;case"testing":return e.colors.primary;default:return e.colors.textSecondary}}};

  .anticon {
    font-size: ${({theme:e})=>e.fontSize.LG}px;
  }
`,wt=r(ye)`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.MD}px;
    border-color: ${({theme:e})=>e.colors.borderSecondary};
    color: ${({theme:e})=>e.colors.textPrimary};
    background-color: ${({theme:e})=>e.colors.bgSecondary};
  }
`;r(p)`
  && {
    text-transform: capitalize;
  }
`;const $t=r(at)`
  && {
    color: ${({theme:e,$isError:t})=>t?e.colors.error:e.colors.textPrimary};
  }
`,Ct=({open:t,onClose:n,machines:i})=>{const{t:s}=$e(["machines","common"]),[r,o]=a.useState([]),[c,l]=a.useState(!1),[m,d]=a.useState(0),[u,h]=a.useState(-1),{executePingForMachine:p,waitForQueueItemCompletion:b}=tt();a.useEffect(()=>{if(t&&i.length>0){const e=i.map(e=>({machineName:e.machineName,teamName:e.teamName,bridgeName:e.bridgeName,status:"pending"}));o(e),d(0),h(-1)}},[t,i]);const j=e=>e.success?s("machines:connectionSuccessful"):"TIMEOUT"===e.status?s("machines:testTimeout"):e.message||s("machines:connectionFailed"),v=async(e,t)=>{const a=Date.now();o(e=>e.map((e,a)=>a===t?{...e,status:"testing",timestamp:(new Date).toISOString()}:e));try{const n=await p(e,{priority:4,description:"Connectivity test",addedVia:"connectivity-test"});if(!n.success||!n.taskId)throw new Error(n.error||"Failed to create test task");{o(e=>e.map((e,a)=>a===t?{...e,taskId:n.taskId}:e));const e=await b(n.taskId),i=Date.now()-a;o(a=>a.map((a,n)=>n===t?{...a,status:e.success?"success":"failed",message:j(e),duration:i}:a))}}catch(n){const e=n instanceof Error?n.message:"Failed to create test task",i=Date.now()-a;o(a=>a.map((a,n)=>n===t?{...a,status:"failed",message:e,duration:i}:a))}},N=me({title:s("machines:team"),dataIndex:"teamName",key:"teamName",renderWrapper:t=>e.jsx(wt,{children:t})}),k=me({title:s("machines:bridge"),dataIndex:"bridgeName",key:"bridgeName",renderWrapper:t=>e.jsx(wt,{children:t})}),w=de({title:s("machines:status"),dataIndex:"status",key:"status",width:140,statusMap:{pending:{color:"default",label:s("machines:pending"),icon:e.jsx(f,{})},testing:{color:"blue",label:s("machines:testing"),icon:e.jsx(te,{spin:!0})},success:{color:"success",label:s("machines:connected"),icon:e.jsx(x,{})},failed:{color:"error",label:s("machines:failed"),icon:e.jsx(ae,{})}}}),$=me({title:s("machines:message"),dataIndex:"message",key:"message",ellipsis:!0,renderText:e=>e||"-"}),C=[{title:s("machines:machineName"),dataIndex:"machineName",key:"machineName",render:(t,a)=>e.jsxs(vt,{"data-testid":`connectivity-machine-${t}`,children:[e.jsx(kt,{$variant:a.status,children:(()=>{switch(a.status){case"testing":return e.jsx(te,{spin:!0,"data-testid":`connectivity-status-icon-testing-${t}`});case"success":return e.jsx(x,{"data-testid":`connectivity-status-icon-success-${t}`});case"failed":return e.jsx(ae,{"data-testid":`connectivity-status-icon-failed-${t}`});default:return e.jsx(f,{"data-testid":`connectivity-status-icon-pending-${t}`})}})()}),e.jsx(Nt,{children:t})]})},N,k,{...w,render:(t,a,n)=>e.jsx("span",{"data-testid":`connectivity-status-tag-${a.machineName}-${t}`,children:w.render?.(t,a,n)})},{title:s("machines:responseTime"),dataIndex:"duration",key:"duration",width:120,render:e=>e?e<1e3?`${e}ms`:`${(e/1e3).toFixed(1)}s`:"-"},{...$,render:(t,a,n)=>{if(!t)return $.render?.(t,a,n);const i=$.render?.(t,a,n);return e.jsx($t,{$isError:"failed"===a.status,children:i})}}];return e.jsx(it,{"data-testid":"connectivity-modal",title:e.jsxs(ot,{children:[e.jsx(U,{}),s("machines:connectivityTest")]}),open:t,onCancel:n,className:g.ExtraLarge,destroyOnHidden:!0,footer:e.jsxs(ct,{children:[e.jsx(lt,{type:"primary",icon:e.jsx(te,{}),onClick:async()=>{l(!0);for(let a=0;a<i.length;a++)h(a),d(Math.round(a/i.length*100)),await v(i[a],a);d(100),l(!1),h(-1);const e=r.filter(e=>"success"===e.status).length,t=r.filter(e=>"failed"===e.status).length;0===t?y("success",s("machines:allMachinesConnected",{count:e})):y("warning",s("machines:machinesConnectedWithFailures",{successCount:e,failedCount:t}))},disabled:c||0===i.length,loading:c,"data-testid":"connectivity-run-test-button",children:s(c?"machines:testing":"machines:runTest")}),e.jsx(be,{title:"Close",children:e.jsx(mt,{icon:e.jsx(ae,{}),onClick:n,"data-testid":"connectivity-close-button","aria-label":"Close"})})]}),children:e.jsx(st,{children:e.jsxs(rt,{children:[c&&e.jsxs(dt,{"data-testid":"connectivity-progress-container",children:[e.jsx(ut,{percent:m,status:"active","data-testid":"connectivity-progress-bar"}),u>=0&&u<i.length&&e.jsx(ht,{"data-testid":"connectivity-progress-text",children:s("machines:testingMachine",{machineName:i[u].machineName})})]}),e.jsx(pt,{message:s("machines:connectivityTestDescription"),type:"info",showIcon:!0,icon:e.jsx(U,{}),"data-testid":"connectivity-info-alert"}),e.jsx(jt,{columns:C,dataSource:r,rowKey:"machineName",pagination:!1,scroll:{y:400},loading:0===i.length,rowClassName:e=>`status-${e.status}`,"data-testid":"connectivity-results-table"}),!c&&r.some(e=>"pending"!==e.status)&&e.jsx(gt,{"data-testid":"connectivity-summary-statistics",children:e.jsxs(xt,{children:[e.jsxs(ft,{"data-testid":"connectivity-total-machines",children:[e.jsxs(yt,{children:[s("machines:totalMachines"),":"]}),e.jsx(bt,{children:i.length})]}),e.jsxs(ft,{"data-testid":"connectivity-connected-count",children:[e.jsxs(yt,{children:[s("machines:connected"),":"]}),e.jsx(bt,{$variant:"success",children:r.filter(e=>"success"===e.status).length})]}),e.jsxs(ft,{"data-testid":"connectivity-failed-count",children:[e.jsxs(yt,{children:[s("machines:failed"),":"]}),e.jsx(bt,{$variant:"error",children:r.filter(e=>"failed"===e.status).length})]}),e.jsxs(ft,{"data-testid":"connectivity-average-response",children:[e.jsxs(yt,{children:[s("machines:averageResponse"),":"]}),e.jsx(bt,{children:(()=>{const e=r.filter(e=>"success"===e.status&&e.duration);if(0===e.length)return"-";const t=e.reduce((e,t)=>e+(t.duration||0),0)/e.length;return t<1e3?`${Math.round(t)}ms`:`${(t/1e3).toFixed(1)}s`})()})]})]})})]})})})},St=(e,t={})=>{const{rowHeight:n=54,headerHeight:i=55,paginationHeight:s=64,containerOffset:r=32,minRows:o=5,maxRows:c=100}=t,[l,m]=a.useState(10),d=a.useRef(null),u=a.useCallback(()=>{if(!e.current)return;const t=e.current.offsetHeight-i-s-r,a=Math.floor(t/n),l=Math.max(o,Math.min(c,a));m(l)},[e,n,i,s,r,o,c]),h=a.useRef(null);return a.useEffect(()=>(h.current=((e,t=300)=>{let a=null;const n=()=>{a&&clearTimeout(a),a=setTimeout(()=>{e()},t)};return n.cancel=()=>{a&&(clearTimeout(a),a=null)},n})(u,300),()=>{h.current?.cancel()}),[u]),a.useEffect(()=>(u(),e.current&&window.ResizeObserver&&(d.current=new ResizeObserver(()=>{h.current?.()}),d.current.observe(e.current)),()=>{d.current&&d.current.disconnect(),h.current?.cancel()}),[u,e]),l},Mt={team:{background:"var(--color-success)",color:"var(--color-text-inverse)"},bridge:{background:"var(--color-primary)",color:"var(--color-text-inverse)"},region:{background:"var(--color-info)",color:"var(--color-text-inverse)"},repo:{background:"var(--color-secondary)",color:"var(--color-text-inverse)"},status:{background:"var(--color-warning)",color:"var(--color-text-inverse)"},grand:{background:"var(--color-secondary)",color:"var(--color-text-inverse)"}},It=r.div`
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

  .machine-table-row--selected td {
    background-color: var(--color-bg-selected);
  }
`,Tt=r.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
`,Rt=r.div`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
  padding: ${({theme:e})=>e.spacing.SM}px ${({theme:e})=>e.spacing.MD}px;
  background-color: var(--color-bg-secondary);
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border: 1px solid var(--color-border-secondary);
  gap: ${({theme:e})=>e.spacing.MD}px;
`,At=r.span`
  font-weight: 600;
  color: var(--color-text-primary);
`,Et=r.div`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
`,Vt=r(ge)`
  && {
    min-width: 42px;
    height: ${b.DIMENSIONS.CONTROL_HEIGHT_SM}px;
    border-radius: ${({theme:e})=>e.borderRadius.SM}px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
`,Dt=r.span`
  width: 1px;
  height: 24px;
  background-color: var(--color-border-secondary);
  margin: 0 ${({theme:e})=>e.spacing.SM}px;
`,Ft=r(je).attrs({image:je.PRESENTED_IMAGE_SIMPLE})`
  margin-top: ${({theme:e})=>e.spacing.XL}px;
`,Ot=r.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XL}px;
`,Pt=r(ve)`
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
`,Lt=r.div`
  display: flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
  padding: ${({theme:e})=>e.spacing.XS}px 0;
`,zt=r.div`
  width: 4px;
  height: ${b.DIMENSIONS.ICON_XL}px;
  border-radius: ${({theme:e})=>e.borderRadius.SM}px;
  background-color: ${({$color:e})=>e||"var(--color-text-secondary)"};
`,Gt=r.span`
  font-size: 18px;
  font-weight: 700;
  color: var(--color-text-primary);
`,_t=r.span`
  font-size: 14px;
  color: var(--color-text-secondary);
`,Bt=r.div`
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
`,Wt=r.div`
  display: flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.LG}px;
`,Qt=r(j)`
  font-size: ${b.DIMENSIONS.ICON_MD}px;
  color: var(--color-primary);
`,Ht=r(Qt)`
  font-size: ${b.DIMENSIONS.ICON_LG}px;
`,Xt=r.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XS}px;
`,qt=r.span`
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
`,Ut=r(ge)`
  && {
    /* Maintain compact pill styling to mirror historical control surface */
    height: ${b.DIMENSIONS.CONTROL_HEIGHT_SM}px;
    border-radius: ${({theme:e})=>e.borderRadius.SM}px;
    display: inline-flex;
    align-items: center;
    gap: ${({theme:e})=>e.spacing.XS}px;
  }
`;r.span`
  font-size: 18px;
  color: ${({$status:e})=>{switch(e){case"online":return"var(--color-success)";case"offline":return"var(--color-text-tertiary)";default:return"var(--color-text-quaternary)"}}};
  display: inline-flex;
  align-items: center;
  justify-content: center;
`;const Kt=r(ye)`
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
`,Zt=r(Kt)`
  && {
    font-size: 16px;
    padding: 4px ${({theme:e})=>e.spacing.MD}px;
  }
`,Yt=r(Ne)`
  && .ant-badge-count {
    background-color: ${({$isPositive:e})=>e?"var(--color-success)":"var(--color-border-secondary)"};
    color: ${({$isPositive:e})=>e?"var(--color-text-inverse)":"var(--color-text-secondary)"};
  }
`,Jt=({teamFilter:s,showActions:r=!0,className:o="",onEditMachine:c,onFunctionsMachine:l,onDeleteMachine:m,enabled:d=!0,onQueueItemCreated:u,onRowClick:h,selectedMachine:p})=>{const{t:g}=$e(["machines","common","functions","resources"]),f=n(),E=t(e=>e.ui.uiMode),V="expert"===E,{executePingForMachineAndWait:D}=tt(),F=a.useRef(null),[O,P]=a.useState("machine"),[L,z]=a.useState([]),G=w(),_=$(),B=$(),[W,Q]=a.useState(!1),[H,X]=a.useState(!1),[q,Z]=a.useState(!1),[Y,J]=a.useState(null),[ee,te]=a.useState(!1);i.useEffect(()=>{"simple"===E&&"machine"!==O&&P("machine")},[E,O]);const{data:ae=[],isLoading:ne,refetch:ie}=Se(s,d),{data:re=[]}=Me(s),oe=St(F,{containerOffset:170,minRows:5,maxRows:50}),ce=ae,he=a.useCallback(e=>Be(e,re.map(e=>({repoGuid:e.repoGuid,repoName:e.repoName,grandGuid:e.grandGuid}))),[re]),xe=a.useCallback(e=>{m&&m(e)},[m]),fe=a.useCallback(e=>{h?h(e):(J(e),te(!0))},[h]),ye=a.useCallback(()=>{te(!1),J(null)},[]),{getFunctionsByCategory:je}=K(),ve=a.useMemo(()=>je("machine").filter(e=>e&&!1!==e.showInMenu&&"mount"!==e.name&&"pull"!==e.name),[je]),Ne=V&&C.isEnabled("assignToCluster"),we=a.useCallback(e=>{e.open&&e.machine?B.open(e.machine):B.close()},[B]),Ie=a.useCallback(e=>{e.open&&e.entityType&&e.entityIdentifier?G.open({entityType:e.entityType,entityIdentifier:e.entityIdentifier,entityName:e.entityName}):G.close()},[G]),Te=i.useMemo(()=>(({t:t,isExpertMode:a,uiMode:n,showActions:i,hasSplitView:s,canAssignToCluster:r,onEditMachine:o,onFunctionsMachine:c,handleDelete:l,handleRowClick:m,executePingForMachineAndWait:d,setAssignClusterModal:u,setAuditTraceModal:h,machineFunctions:p})=>{const g=[],f=me({title:t("machines:machineName"),dataIndex:"machineName",key:"machineName",maxLength:50,sorter:We("machineName"),renderWrapper:t=>e.jsxs(pe,{children:[e.jsx(Qt,{}),e.jsx("strong",{children:t})]})});return g.push(de({title:t("machines:status"),dataIndex:"vaultStatusTime",key:"status",statusMap:{online:{icon:e.jsx(x,{}),label:t("machines:connected"),color:"success"},offline:{icon:e.jsx(He,{}),label:t("machines:connectionFailed"),color:"error"},unknown:{icon:e.jsx(He,{}),label:t("machines:statusUnknown"),color:"default"}},sorter:Qe(e=>{if(!e.vaultStatusTime)return 1/0;const t=new Date(e.vaultStatusTime+"Z");return((new Date).getTime()-t.getTime())/6e4<=3?0:1}),renderValue:(e,t)=>{if(!t.vaultStatusTime)return"unknown";const a=new Date(t.vaultStatusTime+"Z");return((new Date).getTime()-a.getTime())/6e4<=3?"online":"offline"}}),f),s||g.push(me({title:t("machines:team"),dataIndex:"teamName",key:"teamName",width:150,sorter:We("teamName"),renderWrapper:t=>e.jsx(Kt,{$variant:"team",children:t})})),s||(a?g.push(me({title:t("machines:region"),dataIndex:"regionName",key:"regionName",width:150,sorter:We("regionName"),renderText:e=>e||"-",renderWrapper:(t,a)=>"-"===a?e.jsx("span",{children:"-"}):e.jsx(Kt,{$variant:"region",children:t})}),me({title:t("machines:bridge"),dataIndex:"bridgeName",key:"bridgeName",width:150,sorter:We("bridgeName"),renderWrapper:t=>e.jsx(Kt,{$variant:"bridge",children:t})})):"simple"!==n&&g.push(me({title:t("bridges.bridge"),dataIndex:"bridgeName",key:"bridgeName",width:150,sorter:We("bridgeName"),renderWrapper:t=>e.jsx(Kt,{$variant:"bridge",children:t})}))),!s&&r&&g.push({title:t("machines:assignmentStatus.title"),key:"assignmentStatus",width:180,ellipsis:!0,render:(t,a)=>e.jsx(Le,{machine:a})}),s||g.push({title:t("machines:queueItems"),dataIndex:"queueCount",key:"queueCount",width:100,align:"center",sorter:We("queueCount"),render:t=>e.jsx(Yt,{$isPositive:t>0,count:t,showZero:!0})}),i&&g.push(ue({title:t("common:table.actions"),width:b.DIMENSIONS.CARD_WIDTH,renderActions:a=>e.jsx(se,{buttons:[{type:"view",icon:e.jsx(Xe,{}),tooltip:"common:viewDetails",onClick:()=>m(a),variant:"default",testIdSuffix:"view-details"},{type:"edit",icon:e.jsx(Ue,{}),tooltip:"common:actions.edit",onClick:()=>o?.(a)},{type:"remote",icon:e.jsx(Ke,{}),tooltip:"machines:remote",dropdownItems:[{key:"functions",label:t("machines:runAction"),icon:e.jsx(Ke,{}),children:[...p.filter(e=>!1!==e?.showInMenu).map(t=>({key:`function-${t?.name||"unknown"}`,label:e.jsx("span",{title:t?.description||"",children:t?.name||"Unknown"}),onClick:()=>c?.(a,t?.name)})),{type:"divider"},{key:"advanced",label:t("machines:advanced"),icon:e.jsx(Ke,{}),onClick:()=>c?.(a)}]},{key:"test",label:t("machines:connectivityTest"),icon:e.jsx(U,{}),onClick:async()=>{y("info",t("machines:testingConnection"));const e=await d(a,{priority:4,description:"Connectivity test",addedVia:"machine-table",timeout:15e3});e.success?y("success",t("machines:connectionSuccessful")):y("error",e.error||t("machines:connectionFailed"))}},...r?[{key:"assignCluster",label:a.distributedStorageClusterName?t("machines:changeClusterAssignment"):t("machines:assignToCluster"),icon:e.jsx(v,{}),onClick:()=>u({open:!0,machine:a})}]:[]]},{type:"trace",icon:e.jsx(N,{}),tooltip:"machines:trace",onClick:()=>h({open:!0,entityType:"Machine",entityIdentifier:a.machineName,entityName:a.machineName})},{type:"delete",icon:e.jsx(k,{}),tooltip:"common:actions.delete",onClick:()=>l(a),danger:!0},{type:"custom",render:t=>e.jsx(qe,{machine:t.machineName,teamName:t.teamName})}],record:a,idField:"machineName",testIdPrefix:"machine",t:t})})),g})({t:g,isExpertMode:V,uiMode:E,showActions:r,hasSplitView:Boolean(h),canAssignToCluster:Ne,onEditMachine:c,onFunctionsMachine:l,handleDelete:xe,handleRowClick:fe,executePingForMachineAndWait:D,setAssignClusterModal:we,setAuditTraceModal:Ie,machineFunctions:ve}),[g,V,E,r,h,Ne,c,l,xe,fe,D,we,Ie,ve]),Re=Ne?{selectedRowKeys:L,onChange:e=>{z(e)},getCheckboxProps:e=>({disabled:!1,"data-testid":`machine-checkbox-${e.machineName}`})}:void 0,Ae=a.useMemo(()=>{const e={};return"machine"===O||ce.forEach(t=>{let a="";if("bridge"===O)a=t.bridgeName;else if("team"===O)a=t.teamName;else if("region"===O)a=t.regionName||"Unknown";else{if("repo"===O){const a=he(t);if(0===a.length)return;return void a.forEach(a=>{const n=a.name;e[n]||(e[n]=[]),e[n].find(e=>e.machineName===t.machineName)||e[n].push(t)})}if("status"===O){const e=he(t);if(0===e.length)a="No Repos";else{const t=e.some(e=>!e.accessible),n=e.some(e=>e.mounted&&e.docker_running),i=e.some(e=>e.mounted&&!e.docker_running),s=e.some(e=>!e.mounted);a=t?"Inaccessible":n?"Active (Running)":i?"Ready (Stopped)":s?"Not Mounted":"Unknown Status"}}else if("grand"===O){const a=he(t);if(0===a.length)return;return void a.forEach(a=>{let n="No Grand Repo";if(a.grandGuid){const e=re.find(e=>e.repoGuid===a.grandGuid);e&&(n=e.repoName)}e[n]||(e[n]=[]),e[n].find(e=>e.machineName===t.machineName)||e[n].push(t)})}}a&&(e[a]||(e[a]=[]),e[a].push(t))}),e},[ce,O,re,he]);return e.jsxs(It,{className:o,children:["simple"===E?null:e.jsx(Et,{children:e.jsxs(pe,{wrap:!0,size:"small",children:[e.jsx(be,{title:g("machines:machine"),children:e.jsx(Vt,{type:"machine"===O?"primary":"default",icon:e.jsx(j,{}),onClick:()=>P("machine"),"data-testid":"machine-view-toggle-machine","aria-label":g("machines:machine")})}),e.jsx(Dt,{}),e.jsx(be,{title:g("machines:groupByBridge"),children:e.jsx(Vt,{type:"bridge"===O?"primary":"default",icon:e.jsx(v,{}),onClick:()=>P("bridge"),"data-testid":"machine-view-toggle-bridge","aria-label":g("machines:groupByBridge")})}),e.jsx(be,{title:g("machines:groupByTeam"),children:e.jsx(Vt,{type:"team"===O?"primary":"default",icon:e.jsx(S,{}),onClick:()=>P("team"),"data-testid":"machine-view-toggle-team","aria-label":g("machines:groupByTeam")})}),V&&e.jsx(be,{title:g("machines:groupByRegion"),children:e.jsx(Vt,{type:"region"===O?"primary":"default",icon:e.jsx(M,{}),onClick:()=>P("region"),"data-testid":"machine-view-toggle-region","aria-label":g("machines:groupByRegion")})}),e.jsx(be,{title:g("machines:groupByRepo"),children:e.jsx(Vt,{type:"repo"===O?"primary":"default",icon:e.jsx(I,{}),onClick:()=>P("repo"),"data-testid":"machine-view-toggle-repo","aria-label":g("machines:groupByRepo")})}),e.jsx(be,{title:g("machines:groupByStatus"),children:e.jsx(Vt,{type:"status"===O?"primary":"default",icon:e.jsx(T,{}),onClick:()=>P("status"),"data-testid":"machine-view-toggle-status","aria-label":g("machines:groupByStatus")})}),e.jsx(be,{title:g("machines:groupByGrand"),children:e.jsx(Vt,{type:"grand"===O?"primary":"default",icon:e.jsx(Ce,{}),onClick:()=>P("grand"),"data-testid":"machine-view-toggle-grand","aria-label":g("machines:groupByGrand")})})]})}),Ne&&0!==L.length?e.jsxs(Rt,{children:[e.jsxs(pe,{size:"middle",children:[e.jsx(At,{children:g("machines:bulkActions.selected",{count:L.length})}),e.jsx(be,{title:g("common:actions.clearSelection"),children:e.jsx(ge,{size:"small",onClick:()=>z([]),"data-testid":"machine-bulk-clear-selection","aria-label":g("common:actions.clearSelection")})})]}),e.jsxs(pe,{size:"middle",children:[e.jsx(be,{title:g("machines:bulkActions.assignToCluster"),children:e.jsx(ge,{type:"primary",icon:e.jsx(v,{}),onClick:()=>Q(!0),"data-testid":"machine-bulk-assign-cluster","aria-label":g("machines:bulkActions.assignToCluster")})}),e.jsx(be,{title:g("machines:bulkActions.removeFromCluster"),children:e.jsx(ge,{icon:e.jsx(v,{}),onClick:()=>X(!0),"data-testid":"machine-bulk-remove-cluster","aria-label":g("machines:bulkActions.removeFromCluster")})}),e.jsx(be,{title:g("machines:bulkActions.viewAssignmentStatus"),children:e.jsx(ge,{icon:e.jsx(R,{}),onClick:()=>Z(!0),"data-testid":"machine-bulk-view-status","aria-label":g("machines:bulkActions.viewAssignmentStatus")})})]})]}):null,"machine"===O?e.jsx(Tt,{ref:F,children:e.jsx(ke,{columns:Te,dataSource:ce,rowKey:"machineName",loading:ne,scroll:{x:"max-content"},rowSelection:Re,rowClassName:e=>{const t="machine-table-row";return p?.machineName===e.machineName?`${t} machine-table-row--selected`:t},"data-testid":"machine-table",pagination:{pageSize:oe,showSizeChanger:!1,showTotal:(e,t)=>g("common:table.showingRecords",{start:t[0],end:t[1],total:e})},onRow:e=>({"data-testid":`machine-row-${e.machineName}`,onClick:t=>{const a=t.target;a.closest("button")||a.closest(".ant-dropdown")||a.closest(".ant-dropdown-menu")||f(`/machines/${e.machineName}/repos`,{state:{machine:e}})}}),sticky:!0})}):(()=>{if(0===Object.keys(Ae).length)return e.jsx(Ft,{description:g("resources:repos.noRepos")});const t={machine:"repo",bridge:"bridge",team:"team",region:"region",repo:"repo",status:"status",grand:"grand"},a={team:"var(--color-success)",bridge:"var(--color-primary)",region:"var(--color-info)",repo:"var(--color-secondary)",status:"var(--color-warning)",grand:"var(--color-secondary)"},n={bridge:e.jsx(v,{}),team:e.jsx(S,{}),region:e.jsx(M,{}),repo:e.jsx(I,{}),status:e.jsx(T,{}),grand:e.jsx(Ce,{})};return e.jsx(Ot,{children:Object.entries(Ae).map(([i,s],r)=>{const o=t[O],c=a[o];return e.jsxs(Pt,{$isAlternate:r%2==0,children:[e.jsxs(Lt,{children:[e.jsx(zt,{$color:c}),e.jsxs(pe,{size:"small",children:[e.jsxs(Gt,{children:["#",r+1]}),e.jsx(Zt,{$variant:o,icon:n[O],children:i}),e.jsxs(_t,{children:[s.length," ",1===s.length?g("machines:machine"):g("machines:machines")]})]})]}),s.map((t,a)=>e.jsxs(Bt,{$isStriped:a%2!=0,onClick:()=>f(`/machines/${t.machineName}/repos`,{state:{machine:t}}),"data-testid":`grouped-machine-row-${t.machineName}`,children:[e.jsxs(Wt,{children:[e.jsx(Ht,{}),e.jsxs(Xt,{children:[e.jsx(qt,{children:t.machineName}),e.jsxs(pe,{size:"small",children:[e.jsx(Kt,{$variant:"team",children:t.teamName}),t.bridgeName&&e.jsx(Kt,{$variant:"bridge",children:t.bridgeName}),t.regionName&&e.jsx(Kt,{$variant:"region",children:t.regionName})]})]})]}),e.jsx(be,{title:g("machines:viewRepos"),children:e.jsx(Ut,{type:"primary",icon:e.jsx(A,{}),onClick:e=>{e.stopPropagation(),f(`/machines/${t.machineName}/repos`,{state:{machine:t}})},children:g("machines:viewRepos")})})]},t.machineName))]},i)})})})(),e.jsx(Ve,{open:G.isOpen,onCancel:G.close,entityType:G.entityType,entityIdentifier:G.entityIdentifier,entityName:G.entityName}),_.state.data&&e.jsx(le,{open:_.isOpen,onCancel:_.close,machineName:_.state.data.machineName,teamName:_.state.data.teamName,bridgeName:_.state.data.bridgeName,onQueueItemCreated:u}),B.state.data&&e.jsx(ze,{open:B.isOpen,machine:B.state.data,onCancel:B.close,onSuccess:()=>{B.close(),ie()}}),e.jsx(ze,{open:W,machines:ae.filter(e=>L.includes(e.machineName)),onCancel:()=>Q(!1),onSuccess:()=>{Q(!1),z([]),ie()}}),e.jsx(Ge,{open:H,machines:ae.filter(e=>L.includes(e.machineName)),onCancel:()=>X(!1),onSuccess:()=>{X(!1),z([]),ie()}}),e.jsx(_e,{open:q,machines:ae.filter(e=>L.includes(e.machineName)),onCancel:()=>Z(!1)}),!h&&e.jsx(De,{machine:Y,visible:ee,onClose:ye})]})},ea=r.div`
  display: flex;
  height: 100%;
  width: 100%;
  position: relative;
  overflow: hidden;
`,ta=r.div`
  width: ${({$width:e})=>e};
  height: 100%;
  overflow: auto;
  min-width: 300px;
  transition: width 0.3s ease-in-out;
`,aa=r.div`
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
`,na=t=>{const{type:n,selectedResource:i,onResourceSelect:s,isPanelCollapsed:r=!0,onTogglePanelCollapse:o}=t,c=Fe(),[l,m]=a.useState(c),[d,u]=a.useState(!1),[h,p]=a.useState(!1);a.useEffect(()=>{m(c)},[c]),a.useEffect(()=>{if(!i){u(!1);const e=setTimeout(()=>{p(!1)},250);return()=>clearTimeout(e)}p(!0),requestAnimationFrame(()=>{u(!0)})},[i]);const g=e=>{s(e)},x=()=>{s(null)},f=r?Oe.COLLAPSED_WIDTH:l;if("machine"===n){const a=i?`calc(100% - ${f}px)`:"100%";return e.jsxs(ea,{"data-testid":"split-resource-view-container",children:[e.jsx(ta,{$width:a,"data-testid":"split-resource-view-left-panel",children:e.jsx(Jt,{...t,onRowClick:g,selectedMachine:i})}),h&&e.jsx(aa,{$visible:d,$rightOffset:f,onClick:x,"data-testid":"split-resource-view-backdrop"}),i&&e.jsx(Pe,{type:"machineName"in i?"machine":"repoName"in i?"repo":"container",data:i,visible:!0,onClose:x,splitWidth:l,onSplitWidthChange:m,isCollapsed:r,onToggleCollapse:o,collapsedWidth:Oe.COLLAPSED_WIDTH})]})}return null},ia=()=>{const{t:t}=$e(["resources","machines","common"]),[i,r]=we.useModal(),o=s(),c=n(),l=E(),{teams:m,selectedTeams:d,setSelectedTeams:u,isLoading:h}=Ye(),{modalState:p,currentResource:g,openModal:x,closeModal:f}=Ze("machine"),[b,j]=a.useState(null),[v,N]=a.useState(null),[k,w]=a.useState(null),[C,S]=a.useState(!0),[M,I]=a.useState({}),{state:T,open:R,close:A}=V(),q=$(),{data:K=[],refetch:te}=Se(d.length>0?d:void 0,d.length>0),{data:ae=[]}=Me(d.length>0?d:void 0),{data:ne=[]}=Z(d.length>0?d:void 0),ie=Ie(),se=Te(),oe=Re(),ce=Ae(),le=Ee(),{executeAction:me,isExecuting:de}=re();a.useEffect(()=>{const e=o.state;e?.createRepo&&c("/credentials",{state:e,replace:!0})},[o,c]);const ue=e=>{j(e),e&&(N(null),w(null),S(!1))},he=a.useCallback(e=>{et({modal:i,t:t,resourceType:"machine",resourceName:e.machineName,translationNamespace:"machines",onConfirm:()=>ce.mutateAsync({teamName:e.teamName,machineName:e.machineName}),onSuccess:()=>te()})},[ce,i,te,t]),pe=a.useCallback(async e=>{try{if("create"===p.mode){const{autoSetup:a,...n}=e;if(await ie.mutateAsync(n),y("success",t("machines:createSuccess")),a)try{await new Promise(e=>setTimeout(e,500));const a=await me({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,functionName:"setup",params:{datastore_size:"95%",source:"apt-repo",rclone_source:"install-script",docker_source:"docker-repo",install_amd_driver:"auto",install_nvidia_driver:"auto"},priority:3,addedVia:"machine-creation-auto-setup",machineVault:e.machineVault||"{}"});a.success&&(a.taskId?(y("info",t("machines:setupQueued")),R(a.taskId,e.machineName)):a.isQueued&&y("info",t("machines:setupQueuedForSubmission")))}catch{y("warning",t("machines:machineCreatedButSetupFailed"))}f(),te()}else if(g){const t=g.machineName,a=e.machineName;a&&a!==t&&await se.mutateAsync({teamName:g.teamName,currentMachineName:t,newMachineName:a}),e.bridgeName&&e.bridgeName!==g.bridgeName&&await oe.mutateAsync({teamName:g.teamName,machineName:a||t,newBridgeName:e.bridgeName});const n=e.machineVault;n&&n!==g.vaultContent&&await le.mutateAsync({teamName:g.teamName,machineName:a||t,machineVault:n,vaultVersion:g.vaultVersion+1}),f(),te()}}catch{}},[f,ie,g,me,R,te,t,p.mode,oe,se,le]),ge=a.useCallback(async(e,t)=>{if(g)try{await le.mutateAsync({teamName:g.teamName,machineName:g.machineName,machineVault:e,vaultVersion:t}),f(),te()}catch{}},[f,g,te,le]),xe=a.useCallback(async e=>{if(g)try{const a=g.machineName,n=g.bridgeName,i=m.find(e=>e.teamName===g.teamName),s="string"==typeof e.params.repo?e.params.repo:void 0,r={teamName:g.teamName,machineName:a,bridgeName:n,functionName:e.function.name,params:e.params,priority:e.priority,addedVia:"machine-table",teamVault:i?.vaultContent||"{}",machineVault:g.vaultContent||"{}",repoVault:"{}"};if(s){const e=ae.find(e=>e.repoGuid===s);r.repoGuid=e?.repoGuid||s,r.repoVault=e?.repoVault||"{}"}if("pull"===e.function.name){const t="string"==typeof e.params.sourceType?e.params.sourceType:void 0,a="string"==typeof e.params.from?e.params.from:void 0;if("machine"===t&&a){const e=K.find(e=>e.machineName===a);e?.vaultContent&&(r.sourceMachineVault=e.vaultContent)}if("storage"===t&&a){const e=ne.find(e=>e.storageName===a);e?.vaultContent&&(r.sourceStorageVault=e.vaultContent)}}const o=await me(r);f(),o.success?o.taskId?(y("success",t("machines:queueItemCreated")),R(o.taskId,a)):o.isQueued&&y("info",t("resources:messages.highestPriorityQueued",{resourceType:"machine"})):y("error",o.error||t("resources:errors.failedToCreateQueueItem"))}catch{y("error",t("resources:errors.failedToCreateQueueItem"))}},[f,g,me,K,R,ae,ne,t,m]),fe=a.useCallback(async(e,a)=>{const n=Y[a];if(!n)return void y("error",t("resources:errors.functionNotFound"));const i={};n.params&&Object.entries(n.params).forEach(([e,t])=>{t.default&&(i[e]=t.default)});const s=m.find(t=>t.teamName===e.teamName),r={teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,functionName:a,params:i,priority:4,addedVia:"machine-table-quick",teamVault:s?.vaultContent||"{}",machineVault:e.vaultContent||"{}",repoVault:"{}"};try{const a=await me(r);a.success?a.taskId?(y("success",t("machines:queueItemCreated")),R(a.taskId,e.machineName)):a.isQueued&&y("info",t("resources:messages.highestPriorityQueued",{resourceType:"machine"})):y("error",a.error||t("resources:errors.failedToCreateQueueItem")),I(t=>({...t,[e.machineName]:Date.now()}))}catch{y("error",t("resources:errors.failedToCreateQueueItem"))}},[me,R,t,m]),ye=ie.isPending||se.isPending||oe.isPending||de,ve=le.isPending,Ne=p.data??g??void 0;return e.jsxs(e.Fragment,{children:[e.jsx(D,{children:e.jsxs(F,{children:[e.jsx(O,{level:3,children:t("machines:heading",{defaultValue:"Machines"})}),e.jsxs(P,{children:[e.jsx(L,{children:e.jsxs(z,{children:[e.jsx(G,{children:e.jsx(_,{children:e.jsx(Je,{"data-testid":"machines-team-selector",teams:m,selectedTeams:d,onChange:u,loading:h,placeholder:t("teams.selectTeamToView"),style:{width:"100%"}})})}),d.length>0&&e.jsxs(B,{children:[e.jsx(be,{title:t("machines:createMachine"),children:e.jsx(W,{$variant:"primary",icon:e.jsx(Q,{}),"data-testid":"machines-create-machine-button",onClick:()=>x("create"),"aria-label":t("machines:createMachine")})}),e.jsx(be,{title:t("machines:connectivityTest"),children:e.jsx(W,{icon:e.jsx(U,{}),"data-testid":"machines-connectivity-test-button",onClick:()=>q.open(),disabled:0===K.length,"aria-label":t("machines:connectivityTest")})}),e.jsx(be,{title:t("common:actions.refresh"),children:e.jsx(W,{icon:e.jsx(X,{}),"data-testid":"machines-refresh-button",onClick:()=>{te(),I(e=>({...e,_global:Date.now()}))},"aria-label":t("common:actions.refresh")})})]})]})}),e.jsx(H,{children:0===d.length?e.jsx(je,{image:je.PRESENTED_IMAGE_SIMPLE,description:t("teams.selectTeamPrompt"),style:{padding:`${l.spacing.LG}px 0`}}):e.jsx(na,{type:"machine",teamFilter:d,showFilters:!0,showActions:!0,onCreateMachine:()=>x("create"),onEditMachine:e=>x("edit",e),onVaultMachine:e=>x("vault",e),onFunctionsMachine:(e,t)=>{t?fe(e,t):x("create",e)},onDeleteMachine:he,enabled:d.length>0,refreshKeys:M,onQueueItemCreated:(e,t)=>{R(e,t)},selectedResource:b||v||k,onResourceSelect:e=>{e&&"machineName"in e?ue(e):e&&"repoName"in e?(ue(null),N(e),w(null),S(!1)):e&&"id"in e&&"state"in e?(ue(null),N(null),w(e),S(!1)):(ue(null),N(null),w(null))},isPanelCollapsed:C,onTogglePanelCollapse:()=>{S(e=>!e)}})})]})]})}),e.jsx(J,{"data-testid":"machines-machine-modal",open:p.open,onCancel:f,resourceType:"machine",mode:p.mode,existingData:Ne,teamFilter:d.length>0?d:void 0,preselectedFunction:p.preselectedFunction,onSubmit:async e=>{const t=e;await pe(t)},onUpdateVault:"edit"===p.mode?ge:void 0,onFunctionSubmit:e=>xe(e),isSubmitting:ye,isUpdatingVault:ve,functionCategories:["machine","backup"],hiddenParams:[],defaultParams:{}}),e.jsx(ee,{"data-testid":"machines-queue-trace-modal",taskId:T.taskId,open:T.open,onCancel:()=>{const e=T.machineName;A(),e&&I(t=>({...t,[e]:Date.now()})),te()}}),e.jsx(Ct,{"data-testid":"machines-connectivity-test-modal",open:q.isOpen,onClose:q.close,machines:K,teamFilter:d}),r]})};export{ia as default};
