import{j as e}from"./chunk-jIVxg-O4.js";import{r as t,y as r,g as a,H as s,c as o,b as i,$ as n,K as c,ao as d,h as l}from"../index-HayqmFIQ.js";import{f as u,g as p}from"./chunk-DaihG_v-.js";import{H as m,D as h,E as f}from"./chunk-JAgq0Ljn.js";import{C as x}from"./chunk-BI9dZpYP.js";import{D as j}from"./chunk-rlLMHz5I.js";import{C as y}from"./chunk-CntYzmIT.js";import{F as g}from"./chunk-CxeEbkIu.js";import{F as v}from"./chunk-BfdXWzoJ.js";import{f as b,c as $,d as k}from"./chunk-DUE7rinv.js";import"./chunk-D6i1O4E4.js";import{f as w}from"./chunk-DhpoEw86.js";import{M as O,c as S,a as L,T as D,q as M,h as _,D as T,B as C,F as R,s as A}from"./chunk-hmLtEp7h.js";import{d as B,m as I}from"./chunk-CsUqxJyM.js";import{u as z}from"./chunk-DfOmacDz.js";var P,H,U,E={exports:{}},N={},X={};function V(){if(P)return X;P=1,Object.defineProperty(X,"__esModule",{value:!0});return X.default={icon:{tag:"svg",attrs:{viewBox:"64 64 896 896",focusable:"false"},children:[{tag:"path",attrs:{d:"M696 480H544V328c0-4.4-3.6-8-8-8h-48c-4.4 0-8 3.6-8 8v152H328c-4.4 0-8 3.6-8 8v48c0 4.4 3.6 8 8 8h152v152c0 4.4 3.6 8 8 8h48c4.4 0 8-3.6 8-8V544h152c4.4 0 8-3.6 8-8v-48c0-4.4-3.6-8-8-8z"}},{tag:"path",attrs:{d:"M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm0 820c-205.4 0-372-166.6-372-372s166.6-372 372-372 372 166.6 372 372-166.6 372-372 372z"}}]},name:"plus-circle",theme:"outlined"},X}function W(){if(H)return N;H=1,Object.defineProperty(N,"__esModule",{value:!0}),N.default=void 0;var e=function(e,t){if(e&&e.__esModule)return e;if(null===e||"object"!=typeof e&&"function"!=typeof e)return{default:e};var r=o(t);if(r&&r.has(e))return r.get(e);var a={__proto__:null},s=Object.defineProperty&&Object.getOwnPropertyDescriptor;for(var i in e)if("default"!==i&&Object.prototype.hasOwnProperty.call(e,i)){var n=s?Object.getOwnPropertyDescriptor(e,i):null;n&&(n.get||n.set)?Object.defineProperty(a,i,n):a[i]=e[i]}return a.default=e,r&&r.set(e,a),a}(u()),r=s(V()),a=s(t());function s(e){return e&&e.__esModule?e:{default:e}}function o(e){if("function"!=typeof WeakMap)return null;var t=new WeakMap,r=new WeakMap;return(o=function(e){return e?r:t})(e)}function i(){return i=Object.assign?Object.assign.bind():function(e){for(var t=1;t<arguments.length;t++){var r=arguments[t];for(var a in r)Object.prototype.hasOwnProperty.call(r,a)&&(e[a]=r[a])}return e},i.apply(this,arguments)}const n=(t,s)=>e.createElement(a.default,i({},t,{ref:s,icon:r.default})),c=e.forwardRef(n);return N.default=c,N}function F(){return U||(U=1,function(e,t){Object.defineProperty(t,"__esModule",{value:!0}),t.default=void 0;var r;const a=(r=W())&&r.__esModule?r:{default:r};t.default=a,e.exports=a}(E,E.exports)),E.exports}const G=p(F()),J=I`
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
`,K=B(O)`
  .ant-modal-content {
    animation: ${J} 0.3s ease-in-out;
  }
  
  .ant-modal-header {
    padding: ${({theme:e})=>e.spacing.MD}px ${({theme:e})=>e.spacing.LG}px;
    border-bottom: 1px solid ${({theme:e})=>e.colors.borderSecondary};
  }
  
  .ant-modal-body {
    padding: ${({theme:e})=>e.spacing.LG}px;
  }
  
  .ant-modal-footer {
    padding: ${({theme:e})=>e.spacing.MD}px ${({theme:e})=>e.spacing.LG}px;
    border-top: 1px solid ${({theme:e})=>e.colors.borderSecondary};
  }
`,Y=B.div`
  text-align: center;
  padding: ${({theme:e})=>e.spacing.XXXL}px 0;
`,q=B.div`
  margin-top: ${({theme:e})=>e.spacing.MD}px;
  color: ${({theme:e})=>e.colors.textSecondary};
`,Z=B.div`
  width: 100%;
  margin-bottom: ${({theme:e})=>e.spacing.LG}px;
`,Q=B.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
`,ee=B.div`
  display: flex;
  gap: ${({theme:e})=>e.spacing.XL}px;
`,te=B.div`
  display: flex;
  flex-direction: column;
  gap: 0;
`,re=B.span`
  font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
  font-size: ${({theme:e})=>e.fontSize.XL}px;
`,ae=B.span`
  color: ${({$color:e})=>e};
`,{Text:se}=D,oe=({open:t,onCancel:u,entityType:p,entityIdentifier:O,entityName:D})=>{const{t:B}=z(["resources","common"]),I=r(),{data:P,isLoading:H,error:U}=b(p,O,t),E=t=>{const r="var(--color-error)",a="var(--color-text-secondary)";switch(t){case"plus-circle":return e.jsx(ae,{$color:a,children:e.jsx(G,{})});case"edit":return e.jsx(ae,{$color:a,children:e.jsx(f,{})});case"trash":return e.jsx(ae,{$color:r,children:e.jsx(l,{})});case"lock":return e.jsx(ae,{$color:a,children:e.jsx(d,{})});case"key":return e.jsx(ae,{$color:a,children:e.jsx(c,{})});case"users":return e.jsx(ae,{$color:a,children:e.jsx(n,{})});case"check-circle":return e.jsx(ae,{$color:a,children:e.jsx(i,{})});case"x-circle":return e.jsx(ae,{$color:r,children:e.jsx(y,{})});case"database":return e.jsx(ae,{$color:a,children:e.jsx(h,{})});case"hdd":return e.jsx(ae,{$color:a,children:e.jsx(m,{})});case"copy":return e.jsx(ae,{$color:a,children:e.jsx(x,{})});default:return e.jsx(ae,{$color:a,children:e.jsx(o,{})})}},N=e=>{switch(e){case"Deleted":case"Cancelled":return"error";default:return"default"}},X=[{title:B("audit.action"),key:"action",width:150,sorter:$("actionType"),render:(t,r,a)=>e.jsxs(S,{"data-testid":`audit-trace-action-${a}`,children:[E(r.iconHint),e.jsx(L,{color:N(r.actionType),"data-testid":`audit-trace-action-tag-${a}`,children:r.actionType})]})},{title:B("audit.details"),dataIndex:"details",key:"details",ellipsis:!0,sorter:$("details")},{title:B("audit.performedBy"),dataIndex:"performedBy",key:"performedBy",width:200,sorter:$("performedBy"),render:(t,r,a)=>e.jsx("span",{"data-testid":`audit-trace-performed-by-${a}`,children:t||B("audit.system")})},{title:B("audit.timestamp"),dataIndex:"timestamp",key:"timestamp",width:200,sorter:k("timestamp"),render:(t,r,a)=>e.jsxs(S,{direction:"vertical",size:0,"data-testid":`audit-trace-timestamp-${a}`,children:[e.jsx(se,{children:w(t,"datetime")}),e.jsx(se,{type:"secondary",style:{fontSize:12},children:r.timeAgo})]})}];return e.jsx(K,{title:e.jsxs(S,{children:[e.jsx(s,{}),B("audit.title",{name:D||O})]}),open:t,onCancel:u,width:a.DIMENSIONS.MODAL_WIDTH_XL,footer:null,destroyOnHidden:!0,"data-testid":"audit-trace-modal",children:H?e.jsxs(Y,{"data-testid":"audit-trace-loading",children:[e.jsx(M,{size:"large"}),e.jsx(q,{children:B("common:general.loading")})]}):U?e.jsx(_,{message:B("audit.error"),description:U instanceof Error?U.message:B("audit.errorLoading"),type:"error",showIcon:!0,"data-testid":"audit-trace-error-alert"}):P?e.jsxs(e.Fragment,{children:[P.summary&&e.jsx(Z,{"data-testid":"audit-trace-summary",children:e.jsxs(Q,{children:[e.jsxs(ee,{children:[e.jsxs(te,{"data-testid":"audit-trace-total-records",children:[e.jsx(se,{type:"secondary",children:B("audit.totalRecords")}),e.jsx(re,{children:P.summary.totalAuditRecords})]}),e.jsxs(te,{"data-testid":"audit-trace-visible-records",children:[e.jsx(se,{type:"secondary",children:B("audit.visibleRecords")}),e.jsx(re,{children:P.summary.visibleAuditRecords})]}),P.summary.lastActivity&&e.jsxs(te,{"data-testid":"audit-trace-last-activity",children:[e.jsx(se,{type:"secondary",children:B("audit.lastActivity")}),e.jsx(se,{strong:!0,children:new Date(P.summary.lastActivity).toLocaleDateString()})]})]}),e.jsx(T,{menu:{items:[{key:"csv",label:B("audit.exportCSV"),icon:e.jsx(v,{}),onClick:()=>{if(!P?.records||0===P.records.length)return;const e=[["Action","Details","Performed By","Timestamp","Time Ago"].join(","),...P.records.map(e=>[e.actionType,`"${e.details.replace(/"/g,'""')}"`,e.performedBy||"System",w(e.timestamp,"datetime"),e.timeAgo].join(","))].join("\n"),t=new Blob([e],{type:"text/csv;charset=utf-8;"}),r=URL.createObjectURL(t),a=document.createElement("a");a.href=r,a.download=`audit-trace-${p}-${O}-${(new Date).toISOString().split("T")[0]}.csv`,document.body.appendChild(a),a.click(),document.body.removeChild(a),URL.revokeObjectURL(r),A.success(B("audit.exportSuccess",{format:"CSV"}))},"data-testid":"audit-trace-export-csv"},{key:"json",label:B("audit.exportJSON"),icon:e.jsx(g,{}),onClick:()=>{if(!P?.records||0===P.records.length)return;const e={entityType:p,entityIdentifier:O,entityName:D,exportDate:(new Date).toISOString(),summary:P.summary,records:P.records.map(e=>({actionType:e.actionType,details:e.details,performedBy:e.performedBy||"System",timestamp:e.timestamp,timeAgo:e.timeAgo,iconHint:e.iconHint}))},t=JSON.stringify(e,null,2),r=new Blob([t],{type:"application/json"}),a=URL.createObjectURL(r),s=document.createElement("a");s.href=a,s.download=`audit-trace-${p}-${O}-${(new Date).toISOString().split("T")[0]}.json`,document.body.appendChild(s),s.click(),document.body.removeChild(s),URL.revokeObjectURL(a),A.success(B("audit.exportSuccess",{format:"JSON"}))},"data-testid":"audit-trace-export-json"}]},placement:"bottomRight","data-testid":"audit-trace-export-dropdown",children:e.jsx(C,{icon:e.jsx(j,{}),"data-testid":"audit-trace-export-button",style:I.buttonSecondary,children:B("audit.export")})})]})}),e.jsx(R,{columns:X,dataSource:P.records,rowKey:(e,t)=>`${e.timestamp}-${t}`,pagination:{pageSize:10,showSizeChanger:!1,showTotal:(e,t)=>B("common:general.showingRecords",{start:t[0],end:t[1],total:e})},scroll:{x:800},size:"small","data-testid":"audit-trace-table"})]}):null})};export{oe as A};
