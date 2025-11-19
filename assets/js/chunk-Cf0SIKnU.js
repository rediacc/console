import{j as e}from"./chunk-jIVxg-O4.js";import{r as t,u as r,i as a,H as s,d as o,c as i,X as n,K as c,al as d,j as l}from"../index-fHjM-a2j.js";import{f as u,g as m}from"./chunk-DaihG_v-.js";import{b as p,E as h}from"./chunk-BLskOYGH.js";import{H as f,D as x}from"./chunk-ChvD9KbW.js";import{C as j}from"./chunk--oc8JDHa.js";import{D as y}from"./chunk-Bw04oynl.js";import{C as g}from"./chunk-BUTeFJ2e.js";import{F as v}from"./chunk-BTlj-FFU.js";import{F as b}from"./chunk-Bj6OST_2.js";import{f as $}from"./chunk-DVhBN_BK.js";import{d as k,m as w}from"./chunk-CsUqxJyM.js";import{M as O,c as S,a as L,T as D,q as _,h as M,D as C,B as R,F as T,s as A}from"./chunk-DcGI-zRP.js";import{u as I}from"./chunk-DfOmacDz.js";var B,z,P,H={exports:{}},U={},X={};function E(){if(B)return X;B=1,Object.defineProperty(X,"__esModule",{value:!0});return X.default={icon:{tag:"svg",attrs:{viewBox:"64 64 896 896",focusable:"false"},children:[{tag:"path",attrs:{d:"M696 480H544V328c0-4.4-3.6-8-8-8h-48c-4.4 0-8 3.6-8 8v152H328c-4.4 0-8 3.6-8 8v48c0 4.4 3.6 8 8 8h152v152c0 4.4 3.6 8 8 8h48c4.4 0 8-3.6 8-8V544h152c4.4 0 8-3.6 8-8v-48c0-4.4-3.6-8-8-8z"}},{tag:"path",attrs:{d:"M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm0 820c-205.4 0-372-166.6-372-372s166.6-372 372-372 372 166.6 372 372-166.6 372-372 372z"}}]},name:"plus-circle",theme:"outlined"},X}function N(){if(z)return U;z=1,Object.defineProperty(U,"__esModule",{value:!0}),U.default=void 0;var e=function(e,t){if(e&&e.__esModule)return e;if(null===e||"object"!=typeof e&&"function"!=typeof e)return{default:e};var r=o(t);if(r&&r.has(e))return r.get(e);var a={__proto__:null},s=Object.defineProperty&&Object.getOwnPropertyDescriptor;for(var i in e)if("default"!==i&&Object.prototype.hasOwnProperty.call(e,i)){var n=s?Object.getOwnPropertyDescriptor(e,i):null;n&&(n.get||n.set)?Object.defineProperty(a,i,n):a[i]=e[i]}return a.default=e,r&&r.set(e,a),a}(u()),r=s(E()),a=s(t());function s(e){return e&&e.__esModule?e:{default:e}}function o(e){if("function"!=typeof WeakMap)return null;var t=new WeakMap,r=new WeakMap;return(o=function(e){return e?r:t})(e)}function i(){return i=Object.assign?Object.assign.bind():function(e){for(var t=1;t<arguments.length;t++){var r=arguments[t];for(var a in r)Object.prototype.hasOwnProperty.call(r,a)&&(e[a]=r[a])}return e},i.apply(this,arguments)}const n=(t,s)=>e.createElement(a.default,i({},t,{ref:s,icon:r.default})),c=e.forwardRef(n);return U.default=c,U}function V(){return P||(P=1,function(e,t){Object.defineProperty(t,"__esModule",{value:!0}),t.default=void 0;var r;const a=(r=N())&&r.__esModule?r:{default:r};t.default=a,e.exports=a}(H,H.exports)),H.exports}const W=m(V()),F=w`
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
`,G=k(O)`
  .ant-modal-content {
    animation: ${F} 0.3s ease-in-out;
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
`,J=k.div`
  text-align: center;
  padding: ${({theme:e})=>e.spacing.XXXL}px 0;
`,q=k.div`
  margin-top: ${({theme:e})=>e.spacing.MD}px;
  color: ${({theme:e})=>e.colors.textSecondary};
`,K=k.div`
  width: 100%;
  margin-bottom: ${({theme:e})=>e.spacing.LG}px;
`,Y=k.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
`,Q=k.div`
  display: flex;
  gap: ${({theme:e})=>e.spacing.XL}px;
`,Z=k.div`
  display: flex;
  flex-direction: column;
  gap: 0;
`,ee=k.span`
  font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
  font-size: ${({theme:e})=>e.fontSize.XL}px;
`,te=k.span`
  color: ${({$color:e})=>e};
`,{Text:re}=D,ae=({open:t,onCancel:u,entityType:m,entityIdentifier:k,entityName:w})=>{const{t:O}=I(["resources","common"]),D=r(),{data:B,isLoading:z,error:P}=p(m,k,t),H=t=>{const r="var(--color-error)",a="var(--color-text-secondary)";switch(t){case"plus-circle":return e.jsx(te,{$color:a,children:e.jsx(W,{})});case"edit":return e.jsx(te,{$color:a,children:e.jsx(h,{})});case"trash":return e.jsx(te,{$color:r,children:e.jsx(l,{})});case"lock":return e.jsx(te,{$color:a,children:e.jsx(d,{})});case"key":return e.jsx(te,{$color:a,children:e.jsx(c,{})});case"users":return e.jsx(te,{$color:a,children:e.jsx(n,{})});case"check-circle":return e.jsx(te,{$color:a,children:e.jsx(i,{})});case"x-circle":return e.jsx(te,{$color:r,children:e.jsx(g,{})});case"database":return e.jsx(te,{$color:a,children:e.jsx(x,{})});case"hdd":return e.jsx(te,{$color:a,children:e.jsx(f,{})});case"copy":return e.jsx(te,{$color:a,children:e.jsx(j,{})});default:return e.jsx(te,{$color:a,children:e.jsx(o,{})})}},U=e=>{switch(e){case"Deleted":case"Cancelled":return"error";default:return"default"}},X=[{title:O("audit.action"),key:"action",width:150,render:(t,r,a)=>e.jsxs(S,{"data-testid":`audit-trace-action-${a}`,children:[H(r.iconHint),e.jsx(L,{color:U(r.actionType),"data-testid":`audit-trace-action-tag-${a}`,children:r.actionType})]})},{title:O("audit.details"),dataIndex:"details",key:"details",ellipsis:!0},{title:O("audit.performedBy"),dataIndex:"performedBy",key:"performedBy",width:200,render:(t,r,a)=>e.jsx("span",{"data-testid":`audit-trace-performed-by-${a}`,children:t||O("audit.system")})},{title:O("audit.timestamp"),dataIndex:"timestamp",key:"timestamp",width:200,render:(t,r,a)=>e.jsxs(S,{direction:"vertical",size:0,"data-testid":`audit-trace-timestamp-${a}`,children:[e.jsx(re,{children:$(t,"datetime")}),e.jsx(re,{type:"secondary",style:{fontSize:12},children:r.timeAgo})]})}];return e.jsx(G,{title:e.jsxs(S,{children:[e.jsx(s,{}),O("audit.title",{name:w||k})]}),open:t,onCancel:u,width:a.DIMENSIONS.MODAL_WIDTH_XL,footer:null,destroyOnHidden:!0,"data-testid":"audit-trace-modal",children:z?e.jsxs(J,{"data-testid":"audit-trace-loading",children:[e.jsx(_,{size:"large"}),e.jsx(q,{children:O("common:general.loading")})]}):P?e.jsx(M,{message:O("audit.error"),description:P instanceof Error?P.message:O("audit.errorLoading"),type:"error",showIcon:!0,"data-testid":"audit-trace-error-alert"}):B?e.jsxs(e.Fragment,{children:[B.summary&&e.jsx(K,{"data-testid":"audit-trace-summary",children:e.jsxs(Y,{children:[e.jsxs(Q,{children:[e.jsxs(Z,{"data-testid":"audit-trace-total-records",children:[e.jsx(re,{type:"secondary",children:O("audit.totalRecords")}),e.jsx(ee,{children:B.summary.totalAuditRecords})]}),e.jsxs(Z,{"data-testid":"audit-trace-visible-records",children:[e.jsx(re,{type:"secondary",children:O("audit.visibleRecords")}),e.jsx(ee,{children:B.summary.visibleAuditRecords})]}),B.summary.lastActivity&&e.jsxs(Z,{"data-testid":"audit-trace-last-activity",children:[e.jsx(re,{type:"secondary",children:O("audit.lastActivity")}),e.jsx(re,{strong:!0,children:new Date(B.summary.lastActivity).toLocaleDateString()})]})]}),e.jsx(C,{menu:{items:[{key:"csv",label:O("audit.exportCSV"),icon:e.jsx(b,{}),onClick:()=>{if(!B?.records||0===B.records.length)return;const e=[["Action","Details","Performed By","Timestamp","Time Ago"].join(","),...B.records.map(e=>[e.actionType,`"${e.details.replace(/"/g,'""')}"`,e.performedBy||"System",$(e.timestamp,"datetime"),e.timeAgo].join(","))].join("\n"),t=new Blob([e],{type:"text/csv;charset=utf-8;"}),r=URL.createObjectURL(t),a=document.createElement("a");a.href=r,a.download=`audit-trace-${m}-${k}-${(new Date).toISOString().split("T")[0]}.csv`,document.body.appendChild(a),a.click(),document.body.removeChild(a),URL.revokeObjectURL(r),A.success(O("audit.exportSuccess",{format:"CSV"}))},"data-testid":"audit-trace-export-csv"},{key:"json",label:O("audit.exportJSON"),icon:e.jsx(v,{}),onClick:()=>{if(!B?.records||0===B.records.length)return;const e={entityType:m,entityIdentifier:k,entityName:w,exportDate:(new Date).toISOString(),summary:B.summary,records:B.records.map(e=>({actionType:e.actionType,details:e.details,performedBy:e.performedBy||"System",timestamp:e.timestamp,timeAgo:e.timeAgo,iconHint:e.iconHint}))},t=JSON.stringify(e,null,2),r=new Blob([t],{type:"application/json"}),a=URL.createObjectURL(r),s=document.createElement("a");s.href=a,s.download=`audit-trace-${m}-${k}-${(new Date).toISOString().split("T")[0]}.json`,document.body.appendChild(s),s.click(),document.body.removeChild(s),URL.revokeObjectURL(a),A.success(O("audit.exportSuccess",{format:"JSON"}))},"data-testid":"audit-trace-export-json"}]},placement:"bottomRight","data-testid":"audit-trace-export-dropdown",children:e.jsx(R,{icon:e.jsx(y,{}),"data-testid":"audit-trace-export-button",style:D.buttonSecondary,children:O("audit.export")})})]})}),e.jsx(T,{columns:X,dataSource:B.records,rowKey:(e,t)=>`${e.timestamp}-${t}`,pagination:{pageSize:10,showSizeChanger:!1,showTotal:(e,t)=>O("common:general.showingRecords",{start:t[0],end:t[1],total:e})},scroll:{x:800},size:"small","data-testid":"audit-trace-table"})]}):null})};export{ae as A};
