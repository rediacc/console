import{f as e,g as t,j as i}from"./chunk-DXoLy3RZ.js";import{r as a,R as r}from"./chunk-ZRs5Vi2W.js";import{d as o}from"./chunk-m5fYU7UF.js";import{s,aT as n,Y as u,V as c}from"../index-C1snWwcF.js";import{T as d,S as l,i as m,o as p}from"./chunk-2wWKRBEk.js";import{u as g}from"./chunk-BAm789jo.js";import{q as f,u as h}from"./chunk-Do-pLCh9.js";const y=()=>{const i=e(),[r,o]=a.useState([]);a.useEffect(()=>{const e=f.subscribe(e=>{o(e)});return()=>{e()}},[]);const c=async e=>{if(!e.machineName)throw new Error("Machine name is required to submit a queue item");if(!e.bridgeName)throw new Error("Bridge name is required to submit a queue item");if(!e.queueVault)throw new Error("Queue vault payload is required");const t=e.priority&&e.priority>=1&&e.priority<=5?e.priority:3,i={...e,queueVault:n(e.queueVault),priority:t},a=await u.post("/CreateQueueItem",i),r=a.resultSets[1]?.data[0]?.taskId||a.resultSets[1]?.data[0]?.TaskId;return{...a,taskId:r}};return{...t({mutationFn:async e=>{const t=await f.addToQueue(e,c);return 1===e.priority?{queueId:t,isQueued:!0}:{taskId:t,isQueued:!1}},onSuccess:(e,t)=>{i.invalidateQueries({queryKey:["queue-items"]}),i.invalidateQueries({queryKey:["queue-items-bridge",t.bridgeName]}),e.isQueued||e.taskId},onError:e=>{s("error",e.message||"Failed to create queue item")}}),localQueue:r,queueStats:f.getQueueStats(),retryQueueItem:e=>f.retryItem(e),removeFromQueue:e=>f.removeFromQueue(e),clearCompleted:()=>f.clearCompleted(),getQueuePosition:e=>f.getQueuePosition(e),getQueueItem:e=>f.getQueueItem(e),subscribeToQueueItem:(e,t)=>f.subscribeToQueueItem(e,t)}},{Text:$}=d;o(o.div`
  width: 100%;
  text-align: center;
  padding: ${({$padding:e="LG",theme:t})=>t.spacing[e]}px 0;
  ${({$muted:e,theme:t})=>e&&`color: ${t.colors.textSecondary};`}
`)``,o($)`
  && {
    font-size: ${({$size:e="SM",theme:t})=>`${{XS:t.fontSize.XS,SM:t.fontSize.CAPTION,BASE:t.fontSize.SM}[e]}px`};
    color: ${({theme:e})=>e.colors.textSecondary};
  }
`,o($)`
  && {
    font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
    font-size: ${({$size:e="LG",theme:t})=>`${{SM:t.fontSize.SM,BASE:t.fontSize.BASE,LG:t.fontSize.LG,XL:t.fontSize.XL}[e]}px`};
    color: ${({$color:e,$variant:t="default",theme:i})=>{if(e)return e;switch(t){case"success":return i.colors.success;case"warning":return i.colors.warning;case"error":return i.colors.error;case"info":return i.colors.info;default:return i.colors.textPrimary}}};
  }
`,o.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
`,o.div`
  display: flex;
  align-items: ${({$align:e="center"})=>e};
  justify-content: space-between;
  flex-wrap: wrap;
  gap: ${({$spacing:e="MD",theme:t})=>t.spacing[e]}px;
`,o.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,o.div`
  display: flex;
  gap: ${({$spacing:e="SM",theme:t})=>t.spacing[e]}px;
  flex-wrap: wrap;
  justify-content: ${({$justify:e="flex-end"})=>e};
`,o.div`
  display: inline-flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,o.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.MD}px;
  margin-bottom: ${({$margin:e="LG",theme:t})=>t.spacing[e]}px;
`,o(l).attrs({direction:"vertical",size:"large"})`
  width: 100%;
`;const x=o(c)`
  && {
    ${({$hasLabel:e,theme:t})=>e?`\n      min-width: ${t.dimensions.CONTROL_HEIGHT}px;\n      padding: 0 ${t.spacing.SM}px;\n      gap: ${t.spacing.XS}px;\n    `:`\n      width: ${t.dimensions.CONTROL_HEIGHT}px;\n    `}
    min-height: ${({theme:e})=>e.dimensions.CONTROL_HEIGHT}px;
    border-radius: ${({theme:e})=>e.borderRadius.MD}px;
  }
`;o.hr`
  border: none;
  height: 1px;
  width: 100%;
  background-color: ${({theme:e})=>e.colors.borderSecondary};
  margin: ${({theme:e})=>e.spacing.MD}px 0;
`;const b=o.div`
  display: inline-flex;
  align-items: center;
  gap: ${({$gap:e,theme:t})=>t.spacing[e]}px;
`;function S({buttons:e,record:t,idField:a,testIdPrefix:o="",t:s,gap:n="SM"}){const u=t[a],c=String(null!=u?u:""),d=o?`${o}-`:"",l=e.filter(e=>void 0===e.visible||("boolean"==typeof e.visible?e.visible:e.visible(t))),g=e=>s?s(e):e;return i.jsx(b,{$gap:n,children:l.map((e,a)=>{if(function(e){return"custom"===e.type&&"render"in e}(e))return i.jsx(r.Fragment,{children:e.render(t)},`custom-${a}`);const o=!0===e.disabled||"function"==typeof e.disabled&&e.disabled(t),s="function"==typeof e.loading?e.loading(t):e.loading,n="function"==typeof e.testId?e.testId(t):e.testId||(e.testIdSuffix?`${d}${e.testIdSuffix}-${c}`:`${d}${e.type}-${c}`),u=g(e.tooltip),l=e.ariaLabel?g(e.ariaLabel):u,f=e.label?g(e.label):void 0,h=i.jsx(x,{type:e.variant||"default",icon:e.icon,danger:e.danger,disabled:o,onClick:e.onClick?()=>e.onClick?.(t):void 0,loading:s,"data-testid":n,"aria-label":l,$hasLabel:!!f,children:f});return e.dropdownItems?i.jsx(m,{menu:{items:e.dropdownItems,onClick:e.onDropdownClick?({key:i})=>e.onDropdownClick?.(i,t):void 0},trigger:["click"],children:i.jsx(p,{title:u,children:h})},e.type):i.jsx(p,{title:u,children:h},e.type)})})}class w{constructor(e){this.deps=e}async execute(e,t){const i=await this.deps.buildQueueVault({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,functionName:e.functionName,params:e.params,priority:e.priority,description:e.description,addedVia:e.addedVia,teamVault:t,machineVault:e.machineVault,repositoryGuid:e.repositoryGuid,repositoryVault:e.repositoryVault,repositoryLoopbackIp:e.repositoryLoopbackIp,repositoryNetworkMode:e.repositoryNetworkMode,repositoryTag:e.repositoryTag,storageName:e.storageName,storageVault:e.storageVault,sourceMachineVault:e.sourceMachineVault,sourceStorageVault:e.sourceStorageVault,sourceRepositoryVault:e.sourceRepositoryVault,destinationMachineVault:e.destinationMachineVault,destinationStorageVault:e.destinationStorageVault,destinationRepositoryVault:e.destinationRepositoryVault}),a=await this.deps.createQueueItem({teamName:e.teamName,machineName:e.machineName,bridgeName:e.bridgeName,queueVault:i,priority:e.priority});return{success:!0,taskId:a?.taskId,isQueued:a?.isQueued}}}function I(){const{data:e=[]}=g(),{buildQueueVault:t}=h(),i=y(),r=a.useMemo(()=>new w({buildQueueVault:t,createQueueItem:e=>i.mutateAsync(e)}),[t,i]);return{executeAction:a.useCallback(async t=>{try{const i=e.find(e=>e.teamName===t.teamName),a=t.teamVault||i?.vaultContent||"{}";return await r.execute(t,a)}catch(i){return{success:!1,error:i instanceof Error?i.message:"Unknown error"}}},[r,e]),isExecuting:i.isPending}}export{S as A,I as a,y as u};
