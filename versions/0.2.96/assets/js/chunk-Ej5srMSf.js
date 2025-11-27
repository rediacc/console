import{j as e}from"./chunk-DXoLy3RZ.js";import{r as t,ag as r,m as a,L as s,H as o,a1 as i,f as n,d as c,aL as d,a9 as l,bt as u,n as m}from"../index-DFSbVq1d.js";import{f as p,g as h}from"./chunk-ZRs5Vi2W.js";import{H as f,D as x,E as j}from"./chunk-Ca9fJjM-.js";import{C as y}from"./chunk-GZztjas1.js";import{D as g}from"./chunk-DwIK0tiE.js";import{C as v}from"./chunk-Cx6_i40I.js";import{F as b}from"./chunk-Cirox70T.js";import{F as $}from"./chunk-cp-QyJm-.js";import{f as k,c as w,d as S}from"./chunk-Dgbx1UTb.js";import"./chunk-DZV5yM2-.js";import{f as O}from"./chunk-DhpoEw86.js";import{M as L,S as D,d as _,T as M,A as T,i as C,c as R,F as A,s as I}from"./chunk-2wWKRBEk.js";import{d as B,m as z}from"./chunk-m5fYU7UF.js";import{u as H}from"./chunk-BYo3s0jF.js";var P,U,E,N={exports:{}},X={},V={};function W(){if(P)return V;P=1,Object.defineProperty(V,"__esModule",{value:!0});return V.default={icon:{tag:"svg",attrs:{viewBox:"64 64 896 896",focusable:"false"},children:[{tag:"path",attrs:{d:"M696 480H544V328c0-4.4-3.6-8-8-8h-48c-4.4 0-8 3.6-8 8v152H328c-4.4 0-8 3.6-8 8v48c0 4.4 3.6 8 8 8h152v152c0 4.4 3.6 8 8 8h48c4.4 0 8-3.6 8-8V544h152c4.4 0 8-3.6 8-8v-48c0-4.4-3.6-8-8-8z"}},{tag:"path",attrs:{d:"M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm0 820c-205.4 0-372-166.6-372-372s166.6-372 372-372 372 166.6 372 372-166.6 372-372 372z"}}]},name:"plus-circle",theme:"outlined"},V}function F(){if(U)return X;U=1,Object.defineProperty(X,"__esModule",{value:!0}),X.default=void 0;var e=function(e,t){if(e&&e.__esModule)return e;if(null===e||"object"!=typeof e&&"function"!=typeof e)return{default:e};var r=o(t);if(r&&r.has(e))return r.get(e);var a={__proto__:null},s=Object.defineProperty&&Object.getOwnPropertyDescriptor;for(var i in e)if("default"!==i&&Object.prototype.hasOwnProperty.call(e,i)){var n=s?Object.getOwnPropertyDescriptor(e,i):null;n&&(n.get||n.set)?Object.defineProperty(a,i,n):a[i]=e[i]}return a.default=e,r&&r.set(e,a),a}(p()),r=s(W()),a=s(t());function s(e){return e&&e.__esModule?e:{default:e}}function o(e){if("function"!=typeof WeakMap)return null;var t=new WeakMap,r=new WeakMap;return(o=function(e){return e?r:t})(e)}function i(){return i=Object.assign?Object.assign.bind():function(e){for(var t=1;t<arguments.length;t++){var r=arguments[t];for(var a in r)Object.prototype.hasOwnProperty.call(r,a)&&(e[a]=r[a])}return e},i.apply(this,arguments)}const n=(t,s)=>e.createElement(a.default,i({},t,{ref:s,icon:r.default})),c=e.forwardRef(n);return X.default=c,X}function G(){return E||(E=1,function(e,t){Object.defineProperty(t,"__esModule",{value:!0}),t.default=void 0;var r;const a=(r=F())&&r.__esModule?r:{default:r};t.default=a,e.exports=a}(N,N.exports)),N.exports}const J=h(G()),Y=z`
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
`,q=B(L)`
  .ant-modal-content {
    animation: ${Y} 0.3s ease-in-out;
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
`,K=B.div`
  text-align: center;
  padding: ${({theme:e})=>e.spacing.XXXL}px 0;
`,Z=B.div`
  margin-top: ${({theme:e})=>e.spacing.MD}px;
  color: ${({theme:e})=>e.colors.textSecondary};
`,Q=B.div`
  width: 100%;
  margin-bottom: ${({theme:e})=>e.spacing.LG}px;
`,ee=B.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
`,te=B.div`
  display: flex;
  gap: ${({theme:e})=>e.spacing.XL}px;
`,re=B.div`
  display: flex;
  flex-direction: column;
  gap: 0;
`,ae=B.span`
  font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
  font-size: ${({theme:e})=>e.fontSize.XL}px;
`,{Text:se}=M,oe=({open:t,onCancel:p,entityType:h,entityIdentifier:L,entityName:M})=>{const{t:B}=H(["resources","common"]),z=r(),{data:P,isLoading:U,error:E}=k(h,L,t),N=t=>{const r="var(--color-error)",a="var(--color-text-secondary)";switch(t){case"plus-circle":return e.jsx(i,{$color:a,children:e.jsx(J,{})});case"edit":return e.jsx(i,{$color:a,children:e.jsx(j,{})});case"trash":return e.jsx(i,{$color:r,children:e.jsx(m,{})});case"lock":return e.jsx(i,{$color:a,children:e.jsx(u,{})});case"key":return e.jsx(i,{$color:a,children:e.jsx(l,{})});case"users":return e.jsx(i,{$color:a,children:e.jsx(d,{})});case"check-circle":return e.jsx(i,{$color:a,children:e.jsx(c,{})});case"x-circle":return e.jsx(i,{$color:r,children:e.jsx(v,{})});case"database":return e.jsx(i,{$color:a,children:e.jsx(x,{})});case"hdd":return e.jsx(i,{$color:a,children:e.jsx(f,{})});case"copy":return e.jsx(i,{$color:a,children:e.jsx(y,{})});default:return e.jsx(i,{$color:a,children:e.jsx(n,{})})}},X=e=>{switch(e){case"Deleted":case"Cancelled":return"error";default:return"default"}},V=[{title:B("audit.action"),key:"action",width:150,sorter:w("actionType"),render:(t,r,a)=>e.jsxs(D,{"data-testid":`audit-trace-action-${a}`,children:[N(r.iconHint),e.jsx(_,{color:X(r.actionType),"data-testid":`audit-trace-action-tag-${a}`,children:r.actionType})]})},{title:B("audit.details"),dataIndex:"details",key:"details",ellipsis:!0,sorter:w("details")},{title:B("audit.performedBy"),dataIndex:"performedBy",key:"performedBy",width:200,sorter:w("performedBy"),render:(t,r,a)=>e.jsx("span",{"data-testid":`audit-trace-performed-by-${a}`,children:t||B("audit.system")})},{title:B("audit.timestamp"),dataIndex:"timestamp",key:"timestamp",width:200,sorter:S("timestamp"),render:(t,r,a)=>e.jsxs(D,{direction:"vertical",size:0,"data-testid":`audit-trace-timestamp-${a}`,children:[e.jsx(se,{children:O(t,"datetime")}),e.jsx(se,{type:"secondary",style:{fontSize:12},children:r.timeAgo})]})}];return e.jsx(q,{title:e.jsxs(D,{children:[e.jsx(o,{}),B("audit.title",{name:M||L})]}),open:t,onCancel:p,width:a.DIMENSIONS.MODAL_WIDTH_XL,footer:null,destroyOnHidden:!0,"data-testid":"audit-trace-modal",children:U?e.jsxs(K,{"data-testid":"audit-trace-loading",children:[e.jsx(s,{loading:!0,centered:!0,minHeight:160,children:e.jsx("div",{})}),e.jsx(Z,{children:B("common:general.loading")})]}):E?e.jsx(T,{message:B("audit.error"),description:E instanceof Error?E.message:B("audit.errorLoading"),type:"error",showIcon:!0,"data-testid":"audit-trace-error-alert"}):P?e.jsxs(e.Fragment,{children:[P.summary&&e.jsx(Q,{"data-testid":"audit-trace-summary",children:e.jsxs(ee,{children:[e.jsxs(te,{children:[e.jsxs(re,{"data-testid":"audit-trace-total-records",children:[e.jsx(se,{type:"secondary",children:B("audit.totalRecords")}),e.jsx(ae,{children:P.summary.totalAuditRecords})]}),e.jsxs(re,{"data-testid":"audit-trace-visible-records",children:[e.jsx(se,{type:"secondary",children:B("audit.visibleRecords")}),e.jsx(ae,{children:P.summary.visibleAuditRecords})]}),P.summary.lastActivity&&e.jsxs(re,{"data-testid":"audit-trace-last-activity",children:[e.jsx(se,{type:"secondary",children:B("audit.lastActivity")}),e.jsx(se,{strong:!0,children:new Date(P.summary.lastActivity).toLocaleDateString()})]})]}),e.jsx(C,{menu:{items:[{key:"csv",label:B("audit.exportCSV"),icon:e.jsx($,{}),onClick:()=>{if(!P?.records||0===P.records.length)return;const e=[["Action","Details","Performed By","Timestamp","Time Ago"].join(","),...P.records.map(e=>[e.actionType,`"${e.details.replace(/"/g,'""')}"`,e.performedBy||"System",O(e.timestamp,"datetime"),e.timeAgo].join(","))].join("\n"),t=new Blob([e],{type:"text/csv;charset=utf-8;"}),r=URL.createObjectURL(t),a=document.createElement("a");a.href=r,a.download=`audit-trace-${h}-${L}-${(new Date).toISOString().split("T")[0]}.csv`,document.body.appendChild(a),a.click(),document.body.removeChild(a),URL.revokeObjectURL(r),I.success(B("audit.exportSuccess",{format:"CSV"}))},"data-testid":"audit-trace-export-csv"},{key:"json",label:B("audit.exportJSON"),icon:e.jsx(b,{}),onClick:()=>{if(!P?.records||0===P.records.length)return;const e={entityType:h,entityIdentifier:L,entityName:M,exportDate:(new Date).toISOString(),summary:P.summary,records:P.records.map(e=>({actionType:e.actionType,details:e.details,performedBy:e.performedBy||"System",timestamp:e.timestamp,timeAgo:e.timeAgo,iconHint:e.iconHint}))},t=JSON.stringify(e,null,2),r=new Blob([t],{type:"application/json"}),a=URL.createObjectURL(r),s=document.createElement("a");s.href=a,s.download=`audit-trace-${h}-${L}-${(new Date).toISOString().split("T")[0]}.json`,document.body.appendChild(s),s.click(),document.body.removeChild(s),URL.revokeObjectURL(a),I.success(B("audit.exportSuccess",{format:"JSON"}))},"data-testid":"audit-trace-export-json"}]},placement:"bottomRight","data-testid":"audit-trace-export-dropdown",children:e.jsx(R,{icon:e.jsx(g,{}),"data-testid":"audit-trace-export-button",style:z.buttonSecondary,children:B("audit.export")})})]})}),e.jsx(A,{columns:V,dataSource:P.records,rowKey:(e,t)=>`${e.timestamp}-${t}`,pagination:{pageSize:10,showSizeChanger:!1,showTotal:(e,t)=>B("common:general.showingRecords",{start:t[0],end:t[1],total:e})},scroll:{x:800},size:"small","data-testid":"audit-trace-table"})]}):null})};export{oe as A};
