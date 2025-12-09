import{j as e,g as a}from"./chunk-DH1Qig9d.js";import{b as t,f as n,R as s,u as i}from"./chunk-Dx23Oqz1.js";import{d as r,z as o,B as c,M as m,F as l,i as d,A as u,c as h,G as p,f as g,I as x,J as f,K as j,N as b,O as y,Q as v,U as N,l as k,o as C,g as w,V as $,X as S,a as M,D as I,j as T,C as A,H as R,Y as E,Z as D,_ as F,$ as V,T as P,a0 as z,x as O,a1 as L,y as B,a2 as G,a3 as _,n as Q,a4 as W,a5 as q,a6 as X,a7 as U,a8 as H,a9 as K,aa as Z,ab as Y,ac as J,ad as ee,ae}from"../index-ClTVN05S.js";import{u as te,a as ne,b as se,c as ie,d as re,e as oe,f as ce}from"./chunk-D3tHevRZ.js";import{u as me,a as le,F as de,U as ue}from"./chunk-t2k6T-dp.js";import{Q as he}from"./chunk-BJ0l09Ex.js";import{u as pe,T as ge}from"./chunk-C6J8hf5m.js";import{w as xe,u as fe,F as je,b as be,E as ye,M as ve}from"./chunk-CceKb867.js";import{u as Ne}from"./chunk-C6iGxybb.js";import{u as ke,A as Ce,a as we}from"./chunk-BhGhJqp3.js";import{c as $e,a as Se,b as Me}from"./chunk-zgdO0eUg.js";import"./chunk-BHbiZ6Gs.js";import{u as Ie}from"./chunk-BeYBGbaI.js";import{u as Te}from"./chunk-4T_U1bXv.js";import{u as Ae,W as Re}from"./chunk-BwHavVou.js";import{w as Ee,R as De}from"./chunk-95VXPksF.js";import{C as Fe}from"./chunk-luN8MDX4.js";import{S as Ve}from"./chunk-DVvZauX9.js";import{u as Pe}from"./chunk-DsYhoPUY.js";import{A as ze}from"./chunk-Dvtkl8n4.js";import{M as Oe,u as Le,D as Be,U as Ge}from"./chunk-xwOcL0bh.js";import{M as _e,A as Qe,R as We,V as qe}from"./chunk-Dx_92DzT.js";import{g as Xe}from"./chunk-Cl2cMdy5.js";import"./chunk-BNgOMTZp.js";import{B as Ue}from"./chunk-NVvOSgT5.js";import{D as He,E as Ke,L as Ze}from"./chunk-DG6fOAAt.js";import{c as Ye,a as Je}from"./chunk-BKxNWyZX.js";import{E as ea}from"./chunk-CToavtkw.js";import{F as aa}from"./chunk-BgfEUilH.js";import{c as ta}from"./chunk-CLzGX4pd.js";import{R as na}from"./chunk-Cjur1vs7.js";import"./chunk-DB6ez0TU.js";import"./chunk-CWN1N_SP.js";import"./chunk-C187sCeR.js";import"./chunk-SXUH2pe3.js";import"./chunk-DDaRaurs.js";import"./chunk-DhtSDbZF.js";import"./chunk-DlRsp8Cq.js";import"./chunk-DLvxo2sA.js";import"./chunk-CXWedV_K.js";import"./chunk-ei3vgoN9.js";import"./chunk-rVkUBcq2.js";import"./chunk-CSOJ9LX_.js";import"./chunk-Cmj0919L.js";import"./chunk-qT2Z74eY.js";import"./chunk-DRemjfAL.js";import"./chunk-C7fQB5lH.js";import"./chunk-B0Bb5xvy.js";import"./chunk-DhpoEw86.js";import"./chunk-BTmFvS5f.js";import"./chunk-Di7UX9Hu.js";import"./chunk-yhVPGZX_.js";import"./forkTokenService.ts-i5KSIC0Z.js";function sa(e){const{buildQueueVault:a}=Ae();ke();const n=Ie(),{data:s}=Te(),i=t.useCallback(async e=>{try{const t=function(e,a){if(e.teamVault&&"{}"!==e.teamVault)return e.teamVault;const t=a?.find(a=>a.teamName===e.teamName);return t?.vaultContent||"{}"}(e,s),i=await async function(e,a,t){const n=4,s="ping-service",i="{}";return t({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,functionName:"ping",params:{},priority:e.priority||n,addedVia:e.addedVia||s,machineVault:e.machineVault||i,teamVault:a,repositoryVault:e.vaultContent||i})}(e,t,a),r=await async function(e,a,t){const n=4,s=await t.mutateAsync({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,queueVault:a,priority:e.priority||n});return i=s,(e=>{if("object"!=typeof e||null===e)return!1;const a=e,t=void 0===a.taskId||"string"==typeof a.taskId,n=void 0===a.isQueued||"boolean"==typeof a.isQueued;return t&&n})(i)?i:{};var i}(e,i,n);return{taskId:r?.taskId,success:!!r?.taskId||!!r?.isQueued}}catch(t){return{success:!1,error:t instanceof Error?t.message:"Failed to execute ping function"}}},[a,n,s]),r=t.useCallback(async(e,a)=>i({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,priority:a?.priority,description:a?.description,addedVia:a?.addedVia,machineVault:e.vaultContent||"{}"}),[i]),o=t.useCallback(async(e,a)=>{const t=await i(e);if(!t.success||!t.taskId)return t;const n=await Ee(t.taskId,a);return{...t,completionResult:n,success:n.success,error:n.success?void 0:n.message}},[i]),c=t.useCallback(async(e,a)=>o({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,priority:a?.priority,description:a?.description,addedVia:a?.addedVia,machineVault:e.vaultContent||"{}"},a?.timeout),[o]);return{executePing:i,executePingForMachine:r,executePingAndWait:o,executePingForMachineAndWait:c,waitForQueueItemCompletion:Ee,isLoading:n.isPending}}const ia=o`
  0% {
    opacity: 0.65;
  }
  50% {
    opacity: 1;
  }
  100% {
    opacity: 0.65;
  }
`,ra=r(c)`
  .ant-modal-body {
    padding: ${({theme:e})=>e.spacing.XL}px;
  }

  .ant-modal-header {
    .ant-modal-title {
      font-size: ${({theme:e})=>e.fontSize.BASE}px;
      color: ${({theme:e})=>e.colors.textPrimary};

      .anticon {
        font-size: ${({theme:e})=>e.dimensions.ICON_MD}px;
      }
    }
  }
`,oa=r(m)`
  width: 100%;
`,ca=r(l).attrs({$gap:"XS"})``,ma=r(d)`
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
`,la=r.div`
  padding: ${({theme:e})=>e.spacing.MD}px;
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
  background-color: ${({theme:e})=>e.colors.bgSecondary};
`,da=r(u)`
  gap: ${({theme:e})=>e.spacing.XL}px;
`,ua=r(l).attrs({$gap:"XS"})``,ha=r(h).attrs({weight:"semibold"})`
  && {
    color: ${({theme:e,$variant:a})=>"success"===a?e.colors.success:"error"===a?e.colors.error:e.colors.textPrimary};
  }
`,pa=r(p)`
  .status-testing td {
    animation: ${ia} ${({theme:e})=>e.transitions.SLOW};
    background-color: ${({theme:e})=>e.colors.primaryBg};
  }

  .status-success td {
    background-color: ${({theme:e})=>e.colors.bgSuccess};
  }

  .status-failed td {
    background-color: ${({theme:e})=>e.colors.bgError};
  }
`,ga=r(g).attrs({variant:"neutral"})`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.MD}px;
  }
`;r(g)`
  && {
    text-transform: capitalize;
  }
`;const xa=r(h)`
  && {
    color: ${({theme:e,$isError:a})=>a?e.colors.error:e.colors.textPrimary};
  }
`,fa=({open:a,onClose:n,machines:s})=>{const{t:i}=Pe(["machines","common"]),[r,o]=t.useState([]),[c,m]=t.useState(!1),[l,d]=t.useState(0),[u,p]=t.useState(-1),{executePingForMachine:g,waitForQueueItemCompletion:S}=sa();t.useEffect(()=>{if(a&&s.length>0){const e=s.map(e=>({machineName:e.machineName,teamName:e.teamName,bridgeName:e.bridgeName,status:"pending"}));o(e),d(0),p(-1)}},[a,s]);const M=e=>e.success?i("machines:connectionSuccessful"):"TIMEOUT"===e.status?i("machines:testTimeout"):e.message||i("machines:connectionFailed"),I=async(e,a)=>{const t=Date.now();o(e=>e.map((e,t)=>t===a?{...e,status:"testing",timestamp:(new Date).toISOString()}:e));try{const n=await g(e,{priority:4,description:"Connectivity test",addedVia:"connectivity-test"});if(!n.success||!n.taskId)throw new Error(n.error||"Failed to create test task");{o(e=>e.map((e,t)=>t===a?{...e,taskId:n.taskId}:e));const e=await S(n.taskId),s=Date.now()-t;o(t=>t.map((t,n)=>n===a?{...t,status:e.success?"success":"failed",message:M(e),duration:s}:t))}}catch(n){const e=n instanceof Error?n.message:"Failed to create test task",s=Date.now()-t;o(t=>t.map((t,n)=>n===a?{...t,status:"failed",message:e,duration:s}:t))}},T=$e({title:i("machines:team"),dataIndex:"teamName",key:"teamName",renderWrapper:a=>e.jsx(ga,{children:a})}),A=$e({title:i("machines:bridge"),dataIndex:"bridgeName",key:"bridgeName",renderWrapper:a=>e.jsx(ga,{children:a})}),R=Se({title:i("machines:status"),dataIndex:"status",key:"status",width:140,statusMap:{pending:{color:"default",label:i("machines:pending"),icon:e.jsx(w,{})},testing:{color:"blue",label:i("machines:testing"),icon:e.jsx(Ve,{spin:!0})},success:{color:"success",label:i("machines:connected"),icon:e.jsx(C,{})},failed:{color:"error",label:i("machines:failed"),icon:e.jsx(Fe,{})}}}),E=$e({title:i("machines:message"),dataIndex:"message",key:"message",ellipsis:!0,renderText:e=>e||"-"}),D=[{title:i("machines:machineName"),dataIndex:"machineName",key:"machineName",render:(a,t)=>e.jsxs(x,{"data-testid":`connectivity-machine-${a}`,children:[e.jsx(f,{$variant:t.status,children:(()=>{switch(t.status){case"testing":return e.jsx(Ve,{spin:!0,"data-testid":`connectivity-status-icon-testing-${a}`});case"success":return e.jsx(C,{"data-testid":`connectivity-status-icon-success-${a}`});case"failed":return e.jsx(Fe,{"data-testid":`connectivity-status-icon-failed-${a}`});default:return e.jsx(w,{"data-testid":`connectivity-status-icon-pending-${a}`})}})()}),e.jsx(h,{weight:"semibold",children:a})]})},T,A,{...R,render:(a,t,n)=>e.jsx("span",{"data-testid":`connectivity-status-tag-${t.machineName}-${a}`,children:R.render?.(a,t,n)})},{title:i("machines:responseTime"),dataIndex:"duration",key:"duration",width:120,render:e=>e?e<1e3?`${e}ms`:`${(e/1e3).toFixed(1)}s`:"-"},{...E,render:(a,t,n)=>{if(!a)return E.render?.(a,t,n);const s=E.render?.(a,t,n);return e.jsx(xa,{$isError:"failed"===t.status,children:s})}}];return e.jsx(ra,{"data-testid":"connectivity-modal",title:e.jsxs(k,{direction:"horizontal",gap:"sm",align:"center",children:[e.jsx(Re,{}),e.jsx("span",{children:i("machines:connectivityTest")})]}),open:a,onCancel:n,className:j.ExtraLarge,destroyOnClose:!0,footer:e.jsxs(v,{children:[e.jsx(N,{icon:e.jsx(Ve,{}),onClick:async()=>{m(!0);for(let t=0;t<s.length;t++)p(t),d(Math.round(t/s.length*100)),await I(s[t],t);d(100),m(!1),p(-1);const e=r.filter(e=>"success"===e.status).length,a=r.filter(e=>"failed"===e.status).length;0===a?$("success",i("machines:allMachinesConnected",{count:e})):$("warning",i("machines:machinesConnectedWithFailures",{successCount:e,failedCount:a}))},disabled:c||0===s.length,loading:c,"data-testid":"connectivity-run-test-button",children:i(c?"machines:testing":"machines:runTest")}),e.jsx(xe,{title:"Close",children:e.jsx(N,{iconOnly:!0,icon:e.jsx(Fe,{}),onClick:n,"data-testid":"connectivity-close-button","aria-label":"Close"})})]}),children:e.jsx(oa,{children:e.jsxs(b,{children:[c&&e.jsxs(ca,{"data-testid":"connectivity-progress-container",children:[e.jsx(ma,{percent:l,status:"active","data-testid":"connectivity-progress-bar"}),u>=0&&u<s.length&&e.jsx(h,{size:"xs",color:"secondary","data-testid":"connectivity-progress-text",children:i("machines:testingMachine",{machineName:s[u].machineName})})]}),e.jsx(y,{message:i("machines:connectivityTestDescription"),variant:"info",showIcon:!0,icon:e.jsx(Re,{}),"data-testid":"connectivity-info-alert",style:{borderRadius:"12px",fontSize:"14px"}}),e.jsx(pa,{columns:D,dataSource:r,rowKey:"machineName",pagination:!1,scroll:{y:400},loading:0===s.length,rowClassName:e=>`status-${e.status}`,"data-testid":"connectivity-results-table"}),!c&&r.some(e=>"pending"!==e.status)&&e.jsx(la,{"data-testid":"connectivity-summary-statistics",children:e.jsxs(da,{children:[e.jsxs(ua,{"data-testid":"connectivity-total-machines",children:[e.jsxs(h,{color:"secondary",children:[i("machines:totalMachines"),":"]}),e.jsx(ha,{children:s.length})]}),e.jsxs(ua,{"data-testid":"connectivity-connected-count",children:[e.jsxs(h,{color:"secondary",children:[i("machines:connected"),":"]}),e.jsx(ha,{$variant:"success",children:r.filter(e=>"success"===e.status).length})]}),e.jsxs(ua,{"data-testid":"connectivity-failed-count",children:[e.jsxs(h,{color:"secondary",children:[i("machines:failed"),":"]}),e.jsx(ha,{$variant:"error",children:r.filter(e=>"failed"===e.status).length})]}),e.jsxs(ua,{"data-testid":"connectivity-average-response",children:[e.jsxs(h,{color:"secondary",children:[i("machines:averageResponse"),":"]}),e.jsx(ha,{children:(()=>{const e=r.filter(e=>"success"===e.status&&e.duration);if(0===e.length)return"-";const a=e.reduce((e,a)=>e+(a.duration||0),0)/e.length;return a<1e3?`${Math.round(a)}ms`:`${(a/1e3).toFixed(1)}s`})()})]})]})})]})})})},ja=(e,a={})=>{const{rowHeight:n=54,headerHeight:s=55,paginationHeight:i=64,containerOffset:r=32,minRows:o=5,maxRows:c=100}=a,[m,l]=t.useState(10),d=t.useRef(null),u=t.useCallback(()=>{if(!e.current)return;const a=e.current.offsetHeight-s-i-r,t=Math.floor(a/n),m=Math.max(o,Math.min(c,t));l(m)},[e,n,s,i,r,o,c]),h=t.useRef(null);return t.useEffect(()=>(h.current=((e,a=300)=>{let t=null;const n=()=>{t&&clearTimeout(t),t=setTimeout(()=>{e()},a)};return n.cancel=()=>{t&&(clearTimeout(t),t=null)},n})(u,300),()=>{h.current?.cancel()}),[u]),t.useEffect(()=>(u(),e.current&&window.ResizeObserver&&(d.current=new ResizeObserver(()=>{h.current?.()}),d.current.observe(e.current)),()=>{d.current&&d.current.disconnect(),h.current?.cancel()}),[u,e]),m},ba=r(l).attrs({$gap:"MD"})`
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
`,ya=r.div`
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
`,va=r.div`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
  padding: ${({theme:e})=>e.spacing.SM}px ${({theme:e})=>e.spacing.MD}px;
  background-color: var(--color-bg-secondary);
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border: 1px solid var(--color-border-secondary);
  gap: ${({theme:e})=>e.spacing.MD}px;
`,Na=r.span`
  font-weight: 600;
  color: var(--color-text-primary);
`,ka=r.div`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
`,Ca=r(N).attrs({size:"sm"})`
  && {
    min-width: 42px;
  }
`,wa=r.span`
  width: 1px;
  height: 24px;
  background-color: var(--color-border-secondary);
  margin: 0 ${({theme:e})=>e.spacing.SM}px;
`,$a=r.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XL}px;
`,Sa=r(M)`
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
`,Ma=r(x)`
  padding: ${({theme:e})=>e.spacing.XS}px 0;
`,Ia=r.div`
  width: 4px;
  height: ${S.DIMENSIONS.ICON_XL}px;
  border-radius: ${({theme:e})=>e.borderRadius.SM}px;
  background-color: ${({$color:e})=>e||"var(--color-text-secondary)"};
`,Ta=r.span`
  font-size: ${({theme:e})=>e.fontSize.LG}px;
  font-weight: 700;
  color: var(--color-text-primary);
`,Aa=r.span`
  font-size: ${({theme:e})=>e.fontSize.SM}px;
  color: var(--color-text-secondary);
`,Ra=r.div`
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
`,Ea=r.div`
  display: flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.LG}px;
`,Da=r(I)`
  font-size: ${S.DIMENSIONS.ICON_MD}px;
  color: var(--color-primary);
`,Fa=r(Da)`
  font-size: ${S.DIMENSIONS.ICON_LG}px;
`,Va=r.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.XS}px;
`,Pa=r.span`
  font-size: ${({theme:e})=>e.fontSize.BASE}px;
  font-weight: 600;
  color: var(--color-text-primary);
`,za=r(N).attrs({size:"sm"})`
  && {
    /* Maintain compact pill styling to mirror historical control surface */
    gap: ${({theme:e})=>e.spacing.XS}px;
  }
`,Oa=r(g).attrs(({$preset:e,$variant:a})=>({preset:e||a,borderless:!0}))``,La=r(g).attrs(({$preset:e,$variant:a})=>({preset:e||a,borderless:!0,size:"md"}))`
  && {
    font-size: ${({theme:e})=>e.fontSize.BASE}px;
    padding: 4px ${({theme:e})=>e.spacing.MD}px;
  }
`,Ba=r(T)`
  && .ant-badge-count {
    background-color: ${({$isPositive:e})=>e?"var(--color-success)":"var(--color-border-secondary)"};
    color: ${({$isPositive:e})=>e?"var(--color-text-inverse)":"var(--color-text-secondary)"};
  }
`,Ga=({teamFilter:i,showActions:r=!0,className:o="",onEditMachine:c,onFunctionsMachine:m,onDeleteMachine:l,enabled:d=!0,onQueueItemCreated:u,onRowClick:h,selectedMachine:p})=>{const{t:g}=Pe(["machines","common","functions","resources"]),x=n(),f=a(e=>e.ui.uiMode),j="expert"===f,{executePingForMachineAndWait:b}=sa(),y=t.useRef(null),[v,N]=t.useState("machine"),[k,w]=t.useState([]),M=D(),T=F(),Q=F(),[W,q]=t.useState(!1),[X,U]=t.useState(!1),[H,K]=t.useState(!1),[Z,Y]=t.useState(null),[J,ee]=t.useState(!1);s.useEffect(()=>{"simple"===f&&"machine"!==v&&N("machine")},[f,v]);const{data:ae=[],isLoading:se,refetch:ie}=te(i,d),{data:re=[]}=ne(i),oe=ja(y,{containerOffset:170,minRows:5,maxRows:50}),ce=ae,le=t.useCallback(e=>Xe(e,re.map(e=>({repoGuid:e.repoGuid,repoName:e.repoName,grandGuid:e.grandGuid}))),[re]),de=t.useCallback(e=>{l&&l(e)},[l]),ue=t.useCallback(e=>{h?h(e):(Y(e),ee(!0))},[h]),he=t.useCallback(()=>{ee(!1),Y(null)},[]),{getFunctionsByCategory:pe}=me(),ge=t.useMemo(()=>pe("machine").filter(e=>e&&!1!==e.showInMenu&&"mount"!==e.name&&"pull"!==e.name),[pe]),ve=j&&V.isEnabled("assignToCluster"),Ne=t.useCallback(e=>{e.open&&e.machine?Q.open(e.machine):Q.close()},[Q]),ke=t.useCallback(e=>{e.open&&e.entityType&&e.entityIdentifier?M.open({entityType:e.entityType,entityIdentifier:e.entityIdentifier,entityName:e.entityName}):M.close()},[M]),we=s.useMemo(()=>(({t:a,isExpertMode:t,uiMode:n,showActions:s,hasSplitView:i,canAssignToCluster:r,onEditMachine:o,onFunctionsMachine:c,handleDelete:m,handleRowClick:l,executePingForMachineAndWait:d,setAssignClusterModal:u,setAuditTraceModal:h,machineFunctions:p})=>{const g=[],x=$e({title:a("machines:machineName"),dataIndex:"machineName",key:"machineName",maxLength:50,sorter:Ye("machineName"),renderWrapper:a=>e.jsxs(fe,{children:[e.jsx(Da,{}),e.jsx("strong",{children:a})]})});return g.push(Se({title:a("machines:status"),dataIndex:"vaultStatusTime",key:"status",statusMap:{online:{icon:e.jsx(C,{}),label:a("machines:connected"),color:"success"},offline:{icon:e.jsx(He,{}),label:a("machines:connectionFailed"),color:"error"},unknown:{icon:e.jsx(He,{}),label:a("machines:statusUnknown"),color:"default"}},sorter:Je(e=>{if(!e.vaultStatusTime)return 1/0;const a=new Date(e.vaultStatusTime+"Z");return((new Date).getTime()-a.getTime())/6e4<=3?0:1}),renderValue:(e,a)=>{if(!a.vaultStatusTime)return"unknown";const t=new Date(a.vaultStatusTime+"Z");return((new Date).getTime()-t.getTime())/6e4<=3?"online":"offline"}}),x),i||g.push($e({title:a("machines:team"),dataIndex:"teamName",key:"teamName",width:150,sorter:Ye("teamName"),renderWrapper:a=>e.jsx(Oa,{$variant:"team",children:a})})),i||(t?g.push($e({title:a("machines:region"),dataIndex:"regionName",key:"regionName",width:150,sorter:Ye("regionName"),renderText:e=>e||"-",renderWrapper:(a,t)=>"-"===t?e.jsx("span",{children:"-"}):e.jsx(Oa,{$variant:"region",children:a})}),$e({title:a("machines:bridge"),dataIndex:"bridgeName",key:"bridgeName",width:150,sorter:Ye("bridgeName"),renderWrapper:a=>e.jsx(Oa,{$variant:"bridge",children:a})})):"simple"!==n&&g.push($e({title:a("bridges.bridge"),dataIndex:"bridgeName",key:"bridgeName",width:150,sorter:Ye("bridgeName"),renderWrapper:a=>e.jsx(Oa,{$variant:"bridge",children:a})}))),!i&&r&&g.push({title:a("machines:assignmentStatus.title"),key:"assignmentStatus",width:180,ellipsis:!0,render:(a,t)=>e.jsx(_e,{machine:t})}),i||g.push({title:a("machines:queueItems"),dataIndex:"queueCount",key:"queueCount",width:100,align:"center",sorter:Ye("queueCount"),render:a=>e.jsx(Ba,{$isPositive:a>0,count:a,showZero:!0})}),s&&g.push(Me({title:a("common:table.actions"),width:S.DIMENSIONS.CARD_WIDTH,renderActions:t=>e.jsx(Ce,{buttons:[{type:"view",icon:e.jsx(Ke,{}),tooltip:"common:viewDetails",onClick:()=>l(t),variant:"default",testIdSuffix:"view-details"},{type:"edit",icon:e.jsx(ea,{}),tooltip:"common:actions.edit",onClick:()=>o?.(t)},{type:"remote",icon:e.jsx(aa,{}),tooltip:"machines:remote",dropdownItems:[{key:"functions",label:a("machines:runAction"),icon:e.jsx(aa,{}),children:[...p.filter(e=>!1!==e?.showInMenu).map(a=>({key:`function-${a?.name||"unknown"}`,label:e.jsx("span",{title:a?.description||"",children:a?.name||"Unknown"}),onClick:()=>c?.(t,a?.name)})),{type:"divider"},{key:"advanced",label:a("machines:advanced"),icon:e.jsx(aa,{}),onClick:()=>c?.(t)}]},{key:"test",label:a("machines:connectivityTest"),icon:e.jsx(Re,{}),onClick:async()=>{$("info",a("machines:testingConnection"));const e=await d(t,{priority:4,description:"Connectivity test",addedVia:"machine-table",timeout:15e3});e.success?$("success",a("machines:connectionSuccessful")):$("error",e.error||a("machines:connectionFailed"))}},...r?[{key:"assignCluster",label:t.cephClusterName?a("machines:changeClusterAssignment"):a("machines:assignToCluster"),icon:e.jsx(A,{}),onClick:()=>u({open:!0,machine:t})}]:[]]},{type:"trace",icon:e.jsx(R,{}),tooltip:"machines:trace",onClick:()=>h({open:!0,entityType:"Machine",entityIdentifier:t.machineName,entityName:t.machineName})},{type:"delete",icon:e.jsx(E,{}),tooltip:"common:actions.delete",onClick:()=>m(t),danger:!0},{type:"custom",render:a=>e.jsx(Ze,{machine:a.machineName,teamName:a.teamName})}],record:t,idField:"machineName",testIdPrefix:"machine",t:a})})),g})({t:g,isExpertMode:j,uiMode:f,showActions:r,hasSplitView:Boolean(h),canAssignToCluster:ve,onEditMachine:c,onFunctionsMachine:m,handleDelete:de,handleRowClick:ue,executePingForMachineAndWait:b,setAssignClusterModal:Ne,setAuditTraceModal:ke,machineFunctions:ge}),[g,j,f,r,h,ve,c,m,de,ue,b,Ne,ke,ge]),Ie=ve?{selectedRowKeys:k,onChange:e=>{w(e)},getCheckboxProps:e=>({disabled:!1,"data-testid":`machine-checkbox-${e.machineName}`})}:void 0,Te=t.useMemo(()=>{const e={};return"machine"===v||ce.forEach(a=>{let t="";if("bridge"===v)t=a.bridgeName;else if("team"===v)t=a.teamName;else if("region"===v)t=a.regionName||"Unknown";else{if("repo"===v){const t=le(a);if(0===t.length)return;return void t.forEach(t=>{const n=t.name;e[n]||(e[n]=[]),e[n].find(e=>e.machineName===a.machineName)||e[n].push(a)})}if("status"===v){const e=le(a);if(0===e.length)t="No Repos";else{const a=e.some(e=>!e.accessible),n=e.some(e=>e.mounted&&e.docker_running),s=e.some(e=>e.mounted&&!e.docker_running),i=e.some(e=>!e.mounted);t=a?"Inaccessible":n?"Active (Running)":s?"Ready (Stopped)":i?"Not Mounted":"Unknown Status"}}else if("grand"===v){const t=le(a);if(0===t.length)return;return void t.forEach(t=>{let n="No Grand Repo";if(t.grandGuid){const e=re.find(e=>e.repoGuid===t.grandGuid);e&&(n=e.repoName)}e[n]||(e[n]=[]),e[n].find(e=>e.machineName===a.machineName)||e[n].push(a)})}}t&&(e[t]||(e[t]=[]),e[t].push(a))}),e},[ce,v,re,le]);return e.jsxs(ba,{className:o,children:["simple"===f?null:e.jsx(ka,{children:e.jsxs(fe,{wrap:!0,size:"small",children:[e.jsx(xe,{title:g("machines:machine"),children:e.jsx(Ca,{variant:"machine"===v?"primary":"default",icon:e.jsx(I,{}),onClick:()=>N("machine"),"data-testid":"machine-view-toggle-machine","aria-label":g("machines:machine")})}),e.jsx(wa,{}),e.jsx(xe,{title:g("machines:groupByBridge"),children:e.jsx(Ca,{variant:"bridge"===v?"primary":"default",icon:e.jsx(A,{}),onClick:()=>N("bridge"),"data-testid":"machine-view-toggle-bridge","aria-label":g("machines:groupByBridge")})}),e.jsx(xe,{title:g("machines:groupByTeam"),children:e.jsx(Ca,{variant:"team"===v?"primary":"default",icon:e.jsx(P,{}),onClick:()=>N("team"),"data-testid":"machine-view-toggle-team","aria-label":g("machines:groupByTeam")})}),j&&e.jsx(xe,{title:g("machines:groupByRegion"),children:e.jsx(Ca,{variant:"region"===v?"primary":"default",icon:e.jsx(z,{}),onClick:()=>N("region"),"data-testid":"machine-view-toggle-region","aria-label":g("machines:groupByRegion")})}),e.jsx(xe,{title:g("machines:groupByRepo"),children:e.jsx(Ca,{variant:"repo"===v?"primary":"default",icon:e.jsx(O,{}),onClick:()=>N("repo"),"data-testid":"machine-view-toggle-repo","aria-label":g("machines:groupByRepo")})}),e.jsx(xe,{title:g("machines:groupByStatus"),children:e.jsx(Ca,{variant:"status"===v?"primary":"default",icon:e.jsx(L,{}),onClick:()=>N("status"),"data-testid":"machine-view-toggle-status","aria-label":g("machines:groupByStatus")})}),e.jsx(xe,{title:g("machines:groupByGrand"),children:e.jsx(Ca,{variant:"grand"===v?"primary":"default",icon:e.jsx(Ue,{}),onClick:()=>N("grand"),"data-testid":"machine-view-toggle-grand","aria-label":g("machines:groupByGrand")})})]})}),ve&&0!==k.length?e.jsxs(va,{children:[e.jsxs(fe,{size:"middle",children:[e.jsx(Na,{children:g("machines:bulkActions.selected",{count:k.length})}),e.jsx(xe,{title:g("common:actions.clearSelection"),children:e.jsx(be,{size:"small",onClick:()=>w([]),"data-testid":"machine-bulk-clear-selection","aria-label":g("common:actions.clearSelection"),children:"Clear"})})]}),e.jsxs(fe,{size:"middle",children:[e.jsx(xe,{title:g("machines:bulkActions.assignToCluster"),children:e.jsx(be,{type:"primary",icon:e.jsx(A,{}),onClick:()=>q(!0),"data-testid":"machine-bulk-assign-cluster","aria-label":g("machines:bulkActions.assignToCluster")})}),e.jsx(xe,{title:g("machines:bulkActions.removeFromCluster"),children:e.jsx(be,{icon:e.jsx(A,{}),onClick:()=>U(!0),"data-testid":"machine-bulk-remove-cluster","aria-label":g("machines:bulkActions.removeFromCluster")})}),e.jsx(xe,{title:g("machines:bulkActions.viewAssignmentStatus"),children:e.jsx(be,{icon:e.jsx(B,{}),onClick:()=>K(!0),"data-testid":"machine-bulk-view-status","aria-label":g("machines:bulkActions.viewAssignmentStatus")})})]})]}):null,"machine"===v?e.jsx(ya,{ref:y,children:e.jsx(je,{columns:we,dataSource:ce,rowKey:"machineName",loading:se,scroll:{x:"max-content"},rowSelection:Ie,rowClassName:e=>{const a="machine-table-row";return p?.machineName===e.machineName?`${a} machine-table-row--selected`:a},"data-testid":"machine-table",pagination:{pageSize:oe,showSizeChanger:!1,showTotal:(e,a)=>g("common:table.showingRecords",{start:a[0],end:a[1],total:e})},onRow:e=>({"data-testid":`machine-row-${e.machineName}`,onClick:a=>{const t=a.target;t.closest("button")||t.closest(".ant-dropdown")||t.closest(".ant-dropdown-menu")||x(`/machines/${e.machineName}/repos`,{state:{machine:e}})}}),sticky:!0})}):(()=>{if(0===Object.keys(Te).length)return e.jsx(G,{variant:"minimal",image:ye.PRESENTED_IMAGE_SIMPLE,description:g("resources:repos.noRepos"),style:{marginTop:64}});const a={machine:"repo",bridge:"bridge",team:"team",region:"region",repo:"repo",status:"status",grand:"grand"},t={team:"var(--color-success)",bridge:"var(--color-primary)",region:"var(--color-info)",repo:"var(--color-secondary)",status:"var(--color-warning)",grand:"var(--color-secondary)"},n={bridge:e.jsx(A,{}),team:e.jsx(P,{}),region:e.jsx(z,{}),repo:e.jsx(O,{}),status:e.jsx(L,{}),grand:e.jsx(Ue,{})};return e.jsx($a,{children:Object.entries(Te).map(([s,i],r)=>{const o=a[v],c=t[o];return e.jsxs(Sa,{$isAlternate:r%2==0,children:[e.jsxs(Ma,{children:[e.jsx(Ia,{$color:c}),e.jsxs(fe,{size:"small",children:[e.jsxs(Ta,{children:["#",r+1]}),e.jsx(La,{$variant:o,icon:n[v],children:s}),e.jsxs(Aa,{children:[i.length," ",1===i.length?g("machines:machine"):g("machines:machines")]})]})]}),i.map((a,t)=>e.jsxs(Ra,{$isStriped:t%2!=0,onClick:()=>x(`/machines/${a.machineName}/repos`,{state:{machine:a}}),"data-testid":`grouped-machine-row-${a.machineName}`,children:[e.jsxs(Ea,{children:[e.jsx(Fa,{}),e.jsxs(Va,{children:[e.jsx(Pa,{children:a.machineName}),e.jsxs(fe,{size:"small",children:[e.jsx(Oa,{$variant:"team",children:a.teamName}),a.bridgeName&&e.jsx(Oa,{$variant:"bridge",children:a.bridgeName}),a.regionName&&e.jsx(Oa,{$variant:"region",children:a.regionName})]})]})]}),e.jsx(xe,{title:g("machines:viewRepos"),children:e.jsx(za,{variant:"primary",icon:e.jsx(_,{}),onClick:e=>{e.stopPropagation(),x(`/machines/${a.machineName}/repos`,{state:{machine:a}})},children:g("machines:viewRepos")})})]},a.machineName))]},s)})})})(),e.jsx(ze,{open:M.isOpen,onCancel:M.close,entityType:M.entityType,entityIdentifier:M.entityIdentifier,entityName:M.entityName}),T.state.data&&e.jsx(De,{open:T.isOpen,onCancel:T.close,machineName:T.state.data.machineName,teamName:T.state.data.teamName,bridgeName:T.state.data.bridgeName,onQueueItemCreated:u}),Q.state.data&&e.jsx(Qe,{open:Q.isOpen,machine:Q.state.data,onCancel:Q.close,onSuccess:()=>{Q.close(),ie()}}),e.jsx(Qe,{open:W,machines:ae.filter(e=>k.includes(e.machineName)),onCancel:()=>q(!1),onSuccess:()=>{q(!1),w([]),ie()}}),e.jsx(We,{open:X,machines:ae.filter(e=>k.includes(e.machineName)),onCancel:()=>U(!1),onSuccess:()=>{U(!1),w([]),ie()}}),e.jsx(qe,{open:H,machines:ae.filter(e=>k.includes(e.machineName)),onCancel:()=>K(!1)}),!h&&e.jsx(Oe,{machine:Z,visible:J,onClose:he})]})},_a=r.div`
  display: flex;
  height: 100%;
  width: 100%;
  position: relative;
  overflow: hidden;
`,Qa=r.div`
  width: ${({$width:e})=>e};
  height: 100%;
  overflow: auto;
  min-width: 300px;
  transition: width 0.3s ease-in-out;
`,Wa=r.div`
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
`,qa=a=>{const{type:n,selectedResource:s,onResourceSelect:i,isPanelCollapsed:r=!0,onTogglePanelCollapse:o}=a,c=Le(),[m,l]=t.useState(c),[d,u]=t.useState(!1),[h,p]=t.useState(!1);t.useEffect(()=>{l(c)},[c]),t.useEffect(()=>{if(!s){u(!1);const e=setTimeout(()=>{p(!1)},250);return()=>clearTimeout(e)}p(!0),requestAnimationFrame(()=>{u(!0)})},[s]);const g=e=>{i(e)},x=()=>{i(null)},f=r?Be.COLLAPSED_WIDTH:m;if("machine"===n){const t=s?`calc(100% - ${f}px)`:"100%";return e.jsxs(_a,{"data-testid":"split-resource-view-container",children:[e.jsx(Qa,{$width:t,"data-testid":"split-resource-view-left-panel",children:e.jsx(Ga,{...a,onRowClick:g,selectedMachine:s})}),h&&e.jsx(Wa,{$visible:d,$rightOffset:f,onClick:x,"data-testid":"split-resource-view-backdrop"}),s&&e.jsx(Ge,{type:"machineName"in s?"machine":"repoName"in s?"repo":"container",data:s,visible:!0,onClose:x,splitWidth:m,onSplitWidthChange:l,isCollapsed:r,onToggleCollapse:o,collapsedWidth:Be.COLLAPSED_WIDTH})]})}return null},Xa=()=>{const{t:a}=Pe(["resources","machines","common"]),[s,r]=ve.useModal(),o=i(),c=n(),m=Q(),{teams:l,selectedTeams:d,setSelectedTeams:u,isLoading:h}=pe(),{modalState:p,currentResource:g,openModal:x,closeModal:f}=Ne("machine"),[j,b]=t.useState(null),[y,v]=t.useState(null),[k,C]=t.useState(null),[w,S]=t.useState(!0),[M,I]=t.useState({}),{state:T,open:A,close:R}=W(),E=F(),{data:D=[],refetch:V}=te(d.length>0?d:void 0,d.length>0),{data:P=[]}=ne(d.length>0?d:void 0),{data:z=[]}=le(d.length>0?d:void 0),O=se(),L=ie(),B=re(),G=oe(),_=ce(),{executeAction:me,isExecuting:fe}=we();t.useEffect(()=>{const e=o.state;e?.createRepo&&c("/credentials",{state:e,replace:!0})},[o,c]);const je=e=>{b(e),e&&(v(null),C(null),S(!1))},be=t.useCallback(e=>{ta({modal:s,t:a,resourceType:"machine",resourceName:e.machineName,translationNamespace:"machines",onConfirm:()=>G.mutateAsync({teamName:e.teamName,machineName:e.machineName}),onSuccess:()=>V()})},[G,s,V,a]),ke=t.useCallback(async e=>{try{if("create"===p.mode){const{autoSetup:t,...n}=e;if(await O.mutateAsync(n),$("success",a("machines:createSuccess")),t)try{await new Promise(e=>setTimeout(e,500));const t=await me({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,functionName:"setup",params:{datastore_size:"95%",source:"apt-repo",rclone_source:"install-script",docker_source:"docker-repo",install_amd_driver:"auto",install_nvidia_driver:"auto"},priority:3,addedVia:"machine-creation-auto-setup",machineVault:e.vaultContent||"{}"});t.success&&(t.taskId?($("info",a("machines:setupQueued")),A(t.taskId,e.machineName)):t.isQueued&&$("info",a("machines:setupQueuedForSubmission")))}catch{$("warning",a("machines:machineCreatedButSetupFailed"))}f(),V()}else if(g){const a=g.machineName,t=e.machineName;t&&t!==a&&await L.mutateAsync({teamName:g.teamName,currentMachineName:a,newMachineName:t}),e.bridgeName&&e.bridgeName!==g.bridgeName&&await B.mutateAsync({teamName:g.teamName,machineName:t||a,newBridgeName:e.bridgeName});const n=e.vaultContent;n&&n!==g.vaultContent&&await _.mutateAsync({teamName:g.teamName,machineName:t||a,vaultContent:n,vaultVersion:g.vaultVersion+1}),f(),V()}}catch{}},[f,O,g,me,A,V,a,p.mode,B,L,_]),Ce=t.useCallback(async(e,a)=>{if(g)try{await _.mutateAsync({teamName:g.teamName,machineName:g.machineName,vaultContent:e,vaultVersion:a}),f(),V()}catch{}},[f,g,V,_]),$e=t.useCallback(async e=>{if(g)try{const t=g.machineName,n=g.bridgeName,s=l.find(e=>e.teamName===g.teamName),i="string"==typeof e.params.repo?e.params.repo:void 0,r={teamName:g.teamName,machineName:t,bridgeName:n,functionName:e.function.name,params:e.params,priority:e.priority,addedVia:"machine-table",teamVault:s?.vaultContent||"{}",machineVault:g.vaultContent||"{}",vaultContent:"{}"};if(i){const e=P.find(e=>e.repoGuid===i);r.repoGuid=e?.repoGuid||i,r.vaultContent=e?.vaultContent||"{}"}if("pull"===e.function.name){const a="string"==typeof e.params.sourceType?e.params.sourceType:void 0,t="string"==typeof e.params.from?e.params.from:void 0;if("machine"===a&&t){const e=D.find(e=>e.machineName===t);e?.vaultContent&&(r.sourceMachineVault=e.vaultContent)}if("storage"===a&&t){const e=z.find(e=>e.storageName===t);e?.vaultContent&&(r.sourceStorageVault=e.vaultContent)}}const o=await me(r);f(),o.success?o.taskId?($("success",a("machines:queueItemCreated")),A(o.taskId,t)):o.isQueued&&$("info",a("resources:messages.highestPriorityQueued",{resourceType:"machine"})):$("error",o.error||a("resources:errors.failedToCreateQueueItem"))}catch{$("error",a("resources:errors.failedToCreateQueueItem"))}},[f,g,me,D,A,P,z,a,l]),Se=t.useCallback(async(e,t)=>{const n=de[t];if(!n)return void $("error",a("resources:errors.functionNotFound"));const s={};n.params&&Object.entries(n.params).forEach(([e,a])=>{a.default&&(s[e]=a.default)});const i=l.find(a=>a.teamName===e.teamName),r={teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,functionName:t,params:s,priority:4,addedVia:"machine-table-quick",teamVault:i?.vaultContent||"{}",machineVault:e.vaultContent||"{}",vaultContent:"{}"};try{const t=await me(r);t.success?t.taskId?($("success",a("machines:queueItemCreated")),A(t.taskId,e.machineName)):t.isQueued&&$("info",a("resources:messages.highestPriorityQueued",{resourceType:"machine"})):$("error",t.error||a("resources:errors.failedToCreateQueueItem")),I(a=>({...a,[e.machineName]:Date.now()}))}catch{$("error",a("resources:errors.failedToCreateQueueItem"))}},[me,A,a,l]),Me=O.isPending||L.isPending||B.isPending||fe,Ie=_.isPending,Te=p.data??g??void 0;return e.jsxs(e.Fragment,{children:[e.jsx(q,{children:e.jsxs(X,{children:[e.jsx(U,{level:3,children:a("machines:heading",{defaultValue:"Machines"})}),e.jsxs(H,{children:[e.jsx(X,{children:e.jsxs(K,{children:[e.jsx(Z,{children:e.jsx(Y,{children:e.jsx(ge,{"data-testid":"machines-team-selector",teams:l,selectedTeams:d,onChange:u,loading:h,placeholder:a("teams.selectTeamToView"),style:{width:"100%"}})})}),d.length>0&&e.jsxs(J,{children:[e.jsx(xe,{title:a("machines:createMachine"),children:e.jsx(N,{iconOnly:!0,icon:e.jsx(ee,{}),"data-testid":"machines-create-machine-button",onClick:()=>x("create"),"aria-label":a("machines:createMachine")})}),e.jsx(xe,{title:a("machines:connectivityTest"),children:e.jsx(N,{iconOnly:!0,icon:e.jsx(Re,{}),"data-testid":"machines-connectivity-test-button",onClick:()=>E.open(),disabled:0===D.length,"aria-label":a("machines:connectivityTest")})}),e.jsx(xe,{title:a("common:actions.refresh"),children:e.jsx(N,{iconOnly:!0,icon:e.jsx(na,{}),"data-testid":"machines-refresh-button",onClick:()=>{V(),I(e=>({...e,_global:Date.now()}))},"aria-label":a("common:actions.refresh")})})]})]})}),e.jsx(ae,{children:0===d.length?e.jsx(ye,{image:ye.PRESENTED_IMAGE_SIMPLE,description:a("teams.selectTeamPrompt"),style:{padding:`${m.spacing.LG}px 0`}}):e.jsx(qa,{type:"machine",teamFilter:d,showFilters:!0,showActions:!0,onCreateMachine:()=>x("create"),onEditMachine:e=>x("edit",e),onVaultMachine:e=>x("vault",e),onFunctionsMachine:(e,a)=>{a?Se(e,a):x("create",e)},onDeleteMachine:be,enabled:d.length>0,refreshKeys:M,onQueueItemCreated:(e,a)=>{A(e,a)},selectedResource:j||y||k,onResourceSelect:e=>{e&&"machineName"in e?je(e):e&&"repoName"in e?(je(null),v(e),C(null),S(!1)):e&&"id"in e&&"state"in e?(je(null),v(null),C(e),S(!1)):(je(null),v(null),C(null))},isPanelCollapsed:w,onTogglePanelCollapse:()=>{S(e=>!e)}})})]})]})}),e.jsx(ue,{"data-testid":"machines-machine-modal",open:p.open,onCancel:f,resourceType:"machine",mode:p.mode,existingData:Te,teamFilter:d.length>0?d:void 0,preselectedFunction:p.preselectedFunction,onSubmit:async e=>{const a=e;await ke(a)},onUpdateVault:"edit"===p.mode?Ce:void 0,onFunctionSubmit:e=>$e(e),isSubmitting:Me,isUpdatingVault:Ie,functionCategories:["machine","backup"],hiddenParams:[],defaultParams:{}}),e.jsx(he,{"data-testid":"machines-queue-trace-modal",taskId:T.taskId,open:T.open,onCancel:()=>{const e=T.machineName;R(),e&&I(a=>({...a,[e]:Date.now()})),V()}}),e.jsx(fa,{"data-testid":"machines-connectivity-test-modal",open:E.isOpen,onClose:E.close,machines:D,teamFilter:d}),r]})};export{Xa as default};
