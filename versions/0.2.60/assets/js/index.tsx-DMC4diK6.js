import{j as t}from"./chunk-jIVxg-O4.js";import{r as e}from"./chunk-DaihG_v-.js";import{P as s,b as a,c as i}from"../index-DyTMMCCu.js";import{d as o,e as n,E as r}from"./chunk-oGC6pvo6.js";import{D as l}from"./chunk-OvtUXaj_.js";import{S as c}from"./chunk-DeRY2Py9.js";import{R as d}from"./chunk-DsEpBzqB.js";import{C as m}from"./chunk-DAof0Roy.js";import{L as u,S as h}from"./chunk-BVhni6C_.js";import{F as p}from"./chunk-Di9Qi2wT.js";import{F as y}from"./chunk-g3JiB1MS.js";import{T as x,c as f,C as j,B as g,e as w,a as b,l as v,u as Y,v as k,X as C,S,I as D,D as $,h as M,F as H,E as O,s as L}from"./chunk-BKxIVqYm.js";import{d as I}from"./chunk-CsUqxJyM.js";import{F as N}from"./chunk-DbshnkpU.js";import{u as T}from"./chunk-DfOmacDz.js";import"./chunk-BaNBjVcO.js";const{Text:z}=x,A=s,F=I(f).attrs({direction:"vertical",size:"large"})`
  width: 100%;
`,R=I(j).attrs({className:"page-card"})``,B=I(f).attrs({direction:"vertical",size:"small"})`
  width: 100%;
`,U=I(z)`
  && {
    font-size: ${({theme:t})=>t.fontSize.SM}px;
    font-weight: ${({theme:t})=>t.fontWeight.SEMIBOLD};
    color: ${({theme:t})=>t.colors.textPrimary};
  }
`,_=I(U)`
  && {
    color: transparent;
  }
`,E=I(g)`
  width: 100%;
  min-height: ${({theme:t})=>t.spacing[6]}px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
`,P=I(g)`
  min-width: ${({theme:t})=>t.spacing[5]}px;
  min-height: ${({theme:t})=>t.spacing[5]}px;
`,V=I(g).attrs({type:"link"})`
  padding: 0;
  height: auto;
`,J=I(j).attrs({className:"page-card"})``;I.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: ${({theme:t})=>t.spacing.MD}px;
  margin-bottom: ${({theme:t})=>t.spacing.MD}px;
`,I(f)`
  display: flex;
  flex-wrap: wrap;
  gap: ${({theme:t})=>t.spacing.SM}px;
  justify-content: flex-end;
`,I.div`
  text-align: center;
  padding: ${({theme:t})=>t.spacing.LG}px 0;
  color: ${({theme:t})=>t.colors.textSecondary};
`;const X=I(N)`
  font-size: ${({theme:t})=>t.fontSize.CAPTION}px;
  color: ${({theme:t})=>t.colors.textSecondary};
  opacity: 0.7;
`,q=I(N)`
  font-size: ${({theme:t})=>t.fontSize.SM}px;
  color: ${({$active:t,theme:e})=>t?e.colors.textPrimary:e.colors.textTertiary};
  transition: color ${({theme:t})=>t.transitions.FAST};
`,G=I.span`
  display: inline-flex;
  align-items: center;
  color: ${({$color:t})=>t};
  font-size: ${({theme:t})=>t.dimensions.ICON_MD}px;
`,K=I(z)`
  && {
    font-size: ${({theme:t})=>t.fontSize.CAPTION}px;
    color: ${({theme:t})=>t.colors.textSecondary};
  }
`,W=[{keywords:["create"],icon:a,color:"var(--color-success)"},{keywords:["delete"],icon:m,color:"var(--color-error)"},{keywords:["update","modify"],icon:r,color:"var(--color-warning)"},{keywords:["login","auth"],icon:u,color:"var(--color-primary)"},{keywords:["export","import"],icon:h,color:"var(--color-info)"}],{Text:Q}=x,{RangePicker:Z}=C,tt=()=>{const{t:s}=T(["system","common"]),[a,r]=e.useState([w().subtract(7,"days"),w()]),[m,u]=e.useState(),[h,x]=e.useState(""),[j,g]=e.useState(25),[C,I]=e.useState(1),N=a[0]?.startOf("day").format("YYYY-MM-DDTHH:mm:ss"),z=a[1]?.endOf("day").format("YYYY-MM-DDTHH:mm:ss"),{data:tt,isLoading:et,refetch:st,error:at,isError:it}=n({startDate:N,endDate:z,entityFilter:m,maxRecords:1e3}),ot=e.useCallback(e=>{const s=e.toLowerCase(),a=W.find(({keywords:t})=>t.some(t=>s.includes(t)))||{icon:i,color:"var(--color-text-secondary)"},o=a.icon;return t.jsx(G,{$color:a.color,children:t.jsx(o,{})})},[]),nt=e.useCallback(t=>{const e=t.toLowerCase();return e.includes("create")?"success":e.includes("delete")?"error":e.includes("update")||e.includes("modify")?"warning":e.includes("login")||e.includes("auth")?"processing":"default"},[]),rt=tt?.filter(t=>{if(!h)return!0;const e=h.toLowerCase();return t.entityName?.toLowerCase().includes(e)||t.action?.toLowerCase().includes(e)||t.details?.toLowerCase().includes(e)||t.actionByUser?.toLowerCase().includes(e)}),lt=e.useMemo(()=>(({t:e,auditLogs:s,getActionIcon:a,getActionColor:i})=>[{title:e("system:audit.columns.timestamp"),dataIndex:"timestamp",key:"timestamp",width:180,render:t=>w(t).format("YYYY-MM-DD HH:mm:ss"),sorter:o("timestamp"),defaultSortOrder:"descend"},{title:t.jsxs(f,{children:[e("system:audit.columns.action"),t.jsx(X,{})]}),dataIndex:"action",key:"action",width:200,render:e=>t.jsxs(f,{children:[a(e),t.jsx(b,{color:i(e),children:e.replace(/_/g," ")})]}),filters:[...new Set(s?.map(t=>t.action)||[])].map(t=>({text:t.replace(/_/g," "),value:t}))||[],onFilter:(t,e)=>e.action===t,filterIcon:e=>t.jsx(q,{$active:e})},{title:t.jsxs(f,{children:[e("system:audit.columns.entityType"),t.jsx(X,{})]}),dataIndex:"entity",key:"entity",width:160,render:e=>t.jsx(b,{children:e}),filters:[...new Set(s?.map(t=>t.entity)||[])].map(t=>({text:t,value:t}))||[],onFilter:(t,e)=>e.entity===t,filterIcon:e=>t.jsx(q,{$active:e})},{title:t.jsxs(f,{children:[e("system:audit.columns.entityName"),t.jsx(X,{})]}),dataIndex:"entityName",key:"entityName",width:220,filters:[...new Set(s?.map(t=>t.entityName)||[])].map(t=>({text:t,value:t}))||[],onFilter:(t,e)=>e.entityName===t,filterIcon:e=>t.jsx(q,{$active:e}),render:e=>t.jsx(v,{title:e,placement:"topLeft",children:t.jsx("span",{children:e})})},{title:t.jsxs(f,{children:[e("system:audit.columns.user"),t.jsx(X,{})]}),dataIndex:"actionByUser",key:"actionByUser",width:200,filters:[...new Set(s?.map(t=>t.actionByUser)||[])].map(t=>({text:t,value:t}))||[],onFilter:(t,e)=>e.actionByUser===t,filterIcon:e=>t.jsx(q,{$active:e})},{title:e("system:audit.columns.details"),dataIndex:"details",key:"details",ellipsis:!0,render:e=>t.jsx(v,{title:e,placement:"topLeft",children:t.jsx(K,{children:e})})}])({t:s,auditLogs:tt,getActionIcon:ot,getActionColor:nt}),[s,tt,ot,nt]),ct=[...new Set(tt?.map(t=>t.entity)||[])],dt=[{key:"csv",label:t.jsx("span",{"data-testid":"audit-export-csv",children:s("common:exportCSV")}),icon:t.jsx(y,{}),onClick:()=>{if(!rt||0===rt.length)return;const t=[s("system:audit.columns.timestamp"),s("system:audit.columns.action"),s("system:audit.columns.entityType"),s("system:audit.columns.entityName"),s("system:audit.columns.user"),s("system:audit.columns.details")],e=rt.map(t=>[w(t.timestamp).format("YYYY-MM-DD HH:mm:ss"),t.action.replace(/_/g," "),t.entity,t.entityName||"",t.actionByUser,t.details||""]),a=[t.join(","),...e.map(t=>t.map(t=>`"${t}"`).join(","))].join("\n"),i=new Blob([a],{type:"text/csv;charset=utf-8;"}),o=document.createElement("a"),n=URL.createObjectURL(i);o.setAttribute("href",n),o.setAttribute("download",`audit_logs_${w().format("YYYY-MM-DD_HHmmss")}.csv`),o.style.visibility="hidden",document.body.appendChild(o),o.click(),document.body.removeChild(o),L.success(s("system:audit.export.successCSV",{count:rt.length}))}},{key:"json",label:t.jsx("span",{"data-testid":"audit-export-json",children:s("common:exportJSON")}),icon:t.jsx(p,{}),onClick:()=>{if(!rt||0===rt.length)return;const t={exportDate:w().format("YYYY-MM-DD HH:mm:ss"),dateRange:{from:a[0]?.format("YYYY-MM-DD HH:mm:ss"),to:a[1]?.format("YYYY-MM-DD HH:mm:ss")},filters:{entityType:m||"All",searchText:h||"None"},totalRecords:rt.length,logs:rt},e=JSON.stringify(t,null,2),i=new Blob([e],{type:"application/json"}),o=document.createElement("a"),n=URL.createObjectURL(i);o.setAttribute("href",n),o.setAttribute("download",`audit_logs_${w().format("YYYY-MM-DD_HHmmss")}.json`),o.style.visibility="hidden",document.body.appendChild(o),o.click(),document.body.removeChild(o),L.success(s("system:audit.export.successJSON",{count:rt.length}))}}];return t.jsx(A,{children:t.jsxs(F,{children:[t.jsx(R,{"data-testid":"audit-filter-card",children:t.jsx(f,{direction:"vertical",size:"large",children:t.jsxs(Y,{gutter:[24,16],children:[t.jsx(k,{xs:24,sm:24,md:8,children:t.jsxs(B,{children:[t.jsx(U,{children:s("system:audit.filters.dateRange")}),t.jsx(Z,{"data-testid":"audit-filter-date",value:a,onChange:t=>r(t),allowClear:!1,showTime:{format:"HH:mm:ss",defaultValue:[w("00:00:00","HH:mm:ss"),w("23:59:59","HH:mm:ss")]},format:"YYYY-MM-DD HH:mm:ss",presets:[{label:s("common:today"),value:[w().startOf("day"),w().endOf("day")]},{label:s("common:yesterday"),value:[w().subtract(1,"day").startOf("day"),w().subtract(1,"day").endOf("day")]},{label:s("common:last7Days"),value:[w().subtract(7,"day").startOf("day"),w().endOf("day")]},{label:s("common:last30Days"),value:[w().subtract(30,"day").startOf("day"),w().endOf("day")]},{label:s("common:thisMonth"),value:[w().startOf("month"),w().endOf("month")]},{label:s("common:lastMonth"),value:[w().subtract(1,"month").startOf("month"),w().subtract(1,"month").endOf("month")]}]})]})}),t.jsx(k,{xs:24,sm:12,md:6,children:t.jsxs(B,{children:[t.jsx(U,{children:s("system:audit.filters.entityType")}),t.jsx(S,{"data-testid":"audit-filter-entity",placeholder:s("system:audit.filters.allEntities"),allowClear:!0,value:m,onChange:u,options:[{label:s("system:audit.filters.allEntities"),value:void 0},...ct.map(t=>({label:t,value:t}))]})]})}),t.jsx(k,{xs:24,sm:12,md:6,children:t.jsxs(B,{children:[t.jsx(U,{children:s("system:audit.filters.search")}),t.jsx(D,{"data-testid":"audit-filter-search",placeholder:s("system:audit.filters.searchPlaceholder"),prefix:t.jsx(c,{}),value:h,onChange:t=>x(t.target.value),allowClear:!0,autoComplete:"off"})]})}),t.jsx(k,{xs:24,sm:12,md:2,children:t.jsxs(B,{children:[t.jsx(_,{children:s("system:audit.filters.actions")}),t.jsx(E,{"data-testid":"audit-refresh-button",icon:t.jsx(d,{}),onClick:()=>st(),loading:et,children:s("common:actions.refresh")})]})}),t.jsx(k,{xs:24,sm:12,md:2,children:t.jsxs(B,{children:[t.jsx(_,{children:s("system:audit.filters.export")}),t.jsx(v,{title:rt&&0!==rt.length?s("system:audit.export.tooltip"):s("system:audit.export.noData"),children:t.jsx($,{menu:{items:dt},disabled:!rt||0===rt.length,children:t.jsx(E,{"data-testid":"audit-export-button",icon:t.jsx(l,{}),children:s("common:actions.export")})})})]})})]})})}),it&&t.jsx(M,{message:s("system:audit.errors.loadTitle"),description:at?.message||s("system:audit.errors.loadDescription"),type:"error",closable:!0,showIcon:!0,action:t.jsx(P,{size:"small",onClick:()=>st(),loading:et,children:s("system:audit.errors.tryAgain")})}),t.jsx(J,{"data-testid":"audit-table-card",children:t.jsx(H,{"data-testid":"audit-table",columns:lt,dataSource:rt,loading:et,rowKey:t=>`${t.timestamp}-${t.action}-${t.entityName}`,pagination:{current:C,pageSize:j,total:rt?.length||0,showSizeChanger:!0,pageSizeOptions:["10","25","50","100"],showTotal:(t,e)=>s("system:audit.pagination.showing",{start:e[0],end:e[1],total:t}),onChange:(t,e)=>{I(t),e!==j&&(g(e),I(1))},position:["bottomRight"],className:"audit-table-pagination"},scroll:{x:"max-content"},locale:{emptyText:t.jsx(O,{description:t.jsxs(f,{direction:"vertical",align:"center",children:[t.jsx(Q,{type:"secondary",children:it?s("system:audit.errors.unableToLoad"):0===rt?.length&&tt&&tt.length>0?s("system:audit.empty.noMatchingFilters"):s("system:audit.empty.noLogsInRange")}),!it&&t.jsx(V,{onClick:()=>{x(""),u(void 0),r([w().subtract(30,"days"),w()])},children:s("system:audit.empty.clearFilters")})]})})}})})]})})};export{tt as default};
