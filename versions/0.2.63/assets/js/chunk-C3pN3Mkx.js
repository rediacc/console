import{j as e}from"./chunk-DXoLy3RZ.js";import{r as t,K as r,g as a,L as s,H as o,c as i,b as n,a8 as c,O as d,aB as l,h as u}from"../index-CEPyNj08.js";import{f as m,g as p}from"./chunk-ZRs5Vi2W.js";import{H as h,D as f,E as x}from"./chunk-l4qIFyNw.js";import{C as j}from"./chunk-C5BhxkdT.js";import{D as y}from"./chunk-BHjlIAfH.js";import{C as g}from"./chunk-d2k1KcME.js";import{F as v}from"./chunk-Cqaj9b5f.js";import{F as b}from"./chunk-1YaItkzQ.js";import{f as $,c as k,d as w}from"./chunk-D-pnIc8j.js";import"./chunk-Bd12bcfc.js";import{f as O}from"./chunk-DhpoEw86.js";import{M as S,c as L,a as D,T as M,h as _,D as T,B as C,F as R,s as B}from"./chunk-B6OG5Vq-.js";import{d as A,m as I}from"./chunk-BtZST8U3.js";import{u as z}from"./chunk-BYo3s0jF.js";var H,P,U,E={exports:{}},N={},X={};function V(){if(H)return X;H=1,Object.defineProperty(X,"__esModule",{value:!0});return X.default={icon:{tag:"svg",attrs:{viewBox:"64 64 896 896",focusable:"false"},children:[{tag:"path",attrs:{d:"M696 480H544V328c0-4.4-3.6-8-8-8h-48c-4.4 0-8 3.6-8 8v152H328c-4.4 0-8 3.6-8 8v48c0 4.4 3.6 8 8 8h152v152c0 4.4 3.6 8 8 8h48c4.4 0 8-3.6 8-8V544h152c4.4 0 8-3.6 8-8v-48c0-4.4-3.6-8-8-8z"}},{tag:"path",attrs:{d:"M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm0 820c-205.4 0-372-166.6-372-372s166.6-372 372-372 372 166.6 372 372-166.6 372-372 372z"}}]},name:"plus-circle",theme:"outlined"},X}function W(){if(P)return N;P=1,Object.defineProperty(N,"__esModule",{value:!0}),N.default=void 0;var e=function(e,t){if(e&&e.__esModule)return e;if(null===e||"object"!=typeof e&&"function"!=typeof e)return{default:e};var r=o(t);if(r&&r.has(e))return r.get(e);var a={__proto__:null},s=Object.defineProperty&&Object.getOwnPropertyDescriptor;for(var i in e)if("default"!==i&&Object.prototype.hasOwnProperty.call(e,i)){var n=s?Object.getOwnPropertyDescriptor(e,i):null;n&&(n.get||n.set)?Object.defineProperty(a,i,n):a[i]=e[i]}return a.default=e,r&&r.set(e,a),a}(m()),r=s(V()),a=s(t());function s(e){return e&&e.__esModule?e:{default:e}}function o(e){if("function"!=typeof WeakMap)return null;var t=new WeakMap,r=new WeakMap;return(o=function(e){return e?r:t})(e)}function i(){return i=Object.assign?Object.assign.bind():function(e){for(var t=1;t<arguments.length;t++){var r=arguments[t];for(var a in r)Object.prototype.hasOwnProperty.call(r,a)&&(e[a]=r[a])}return e},i.apply(this,arguments)}const n=(t,s)=>e.createElement(a.default,i({},t,{ref:s,icon:r.default})),c=e.forwardRef(n);return N.default=c,N}function F(){return U||(U=1,function(e,t){Object.defineProperty(t,"__esModule",{value:!0}),t.default=void 0;var r;const a=(r=W())&&r.__esModule?r:{default:r};t.default=a,e.exports=a}(E,E.exports)),E.exports}const G=p(F()),J=I`
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
`,K=A(S)`
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
`,Y=A.div`
  text-align: center;
  padding: ${({theme:e})=>e.spacing.XXXL}px 0;
`,Z=A.div`
  margin-top: ${({theme:e})=>e.spacing.MD}px;
  color: ${({theme:e})=>e.colors.textSecondary};
`,q=A.div`
  width: 100%;
  margin-bottom: ${({theme:e})=>e.spacing.LG}px;
`,Q=A.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
`,ee=A.div`
  display: flex;
  gap: ${({theme:e})=>e.spacing.XL}px;
`,te=A.div`
  display: flex;
  flex-direction: column;
  gap: 0;
`,re=A.span`
  font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
  font-size: ${({theme:e})=>e.fontSize.XL}px;
`,ae=A.span`
  color: ${({$color:e})=>e};
`,{Text:se}=M,oe=({open:t,onCancel:m,entityType:p,entityIdentifier:S,entityName:M})=>{const{t:A}=z(["resources","common"]),I=r(),{data:H,isLoading:P,error:U}=$(p,S,t),E=t=>{const r="var(--color-error)",a="var(--color-text-secondary)";switch(t){case"plus-circle":return e.jsx(ae,{$color:a,children:e.jsx(G,{})});case"edit":return e.jsx(ae,{$color:a,children:e.jsx(x,{})});case"trash":return e.jsx(ae,{$color:r,children:e.jsx(u,{})});case"lock":return e.jsx(ae,{$color:a,children:e.jsx(l,{})});case"key":return e.jsx(ae,{$color:a,children:e.jsx(d,{})});case"users":return e.jsx(ae,{$color:a,children:e.jsx(c,{})});case"check-circle":return e.jsx(ae,{$color:a,children:e.jsx(n,{})});case"x-circle":return e.jsx(ae,{$color:r,children:e.jsx(g,{})});case"database":return e.jsx(ae,{$color:a,children:e.jsx(f,{})});case"hdd":return e.jsx(ae,{$color:a,children:e.jsx(h,{})});case"copy":return e.jsx(ae,{$color:a,children:e.jsx(j,{})});default:return e.jsx(ae,{$color:a,children:e.jsx(i,{})})}},N=e=>{switch(e){case"Deleted":case"Cancelled":return"error";default:return"default"}},X=[{title:A("audit.action"),key:"action",width:150,sorter:k("actionType"),render:(t,r,a)=>e.jsxs(L,{"data-testid":`audit-trace-action-${a}`,children:[E(r.iconHint),e.jsx(D,{color:N(r.actionType),"data-testid":`audit-trace-action-tag-${a}`,children:r.actionType})]})},{title:A("audit.details"),dataIndex:"details",key:"details",ellipsis:!0,sorter:k("details")},{title:A("audit.performedBy"),dataIndex:"performedBy",key:"performedBy",width:200,sorter:k("performedBy"),render:(t,r,a)=>e.jsx("span",{"data-testid":`audit-trace-performed-by-${a}`,children:t||A("audit.system")})},{title:A("audit.timestamp"),dataIndex:"timestamp",key:"timestamp",width:200,sorter:w("timestamp"),render:(t,r,a)=>e.jsxs(L,{direction:"vertical",size:0,"data-testid":`audit-trace-timestamp-${a}`,children:[e.jsx(se,{children:O(t,"datetime")}),e.jsx(se,{type:"secondary",style:{fontSize:12},children:r.timeAgo})]})}];return e.jsx(K,{title:e.jsxs(L,{children:[e.jsx(o,{}),A("audit.title",{name:M||S})]}),open:t,onCancel:m,width:a.DIMENSIONS.MODAL_WIDTH_XL,footer:null,destroyOnHidden:!0,"data-testid":"audit-trace-modal",children:P?e.jsxs(Y,{"data-testid":"audit-trace-loading",children:[e.jsx(s,{loading:!0,centered:!0,minHeight:160,children:e.jsx("div",{})}),e.jsx(Z,{children:A("common:general.loading")})]}):U?e.jsx(_,{message:A("audit.error"),description:U instanceof Error?U.message:A("audit.errorLoading"),type:"error",showIcon:!0,"data-testid":"audit-trace-error-alert"}):H?e.jsxs(e.Fragment,{children:[H.summary&&e.jsx(q,{"data-testid":"audit-trace-summary",children:e.jsxs(Q,{children:[e.jsxs(ee,{children:[e.jsxs(te,{"data-testid":"audit-trace-total-records",children:[e.jsx(se,{type:"secondary",children:A("audit.totalRecords")}),e.jsx(re,{children:H.summary.totalAuditRecords})]}),e.jsxs(te,{"data-testid":"audit-trace-visible-records",children:[e.jsx(se,{type:"secondary",children:A("audit.visibleRecords")}),e.jsx(re,{children:H.summary.visibleAuditRecords})]}),H.summary.lastActivity&&e.jsxs(te,{"data-testid":"audit-trace-last-activity",children:[e.jsx(se,{type:"secondary",children:A("audit.lastActivity")}),e.jsx(se,{strong:!0,children:new Date(H.summary.lastActivity).toLocaleDateString()})]})]}),e.jsx(T,{menu:{items:[{key:"csv",label:A("audit.exportCSV"),icon:e.jsx(b,{}),onClick:()=>{if(!H?.records||0===H.records.length)return;const e=[["Action","Details","Performed By","Timestamp","Time Ago"].join(","),...H.records.map(e=>[e.actionType,`"${e.details.replace(/"/g,'""')}"`,e.performedBy||"System",O(e.timestamp,"datetime"),e.timeAgo].join(","))].join("\n"),t=new Blob([e],{type:"text/csv;charset=utf-8;"}),r=URL.createObjectURL(t),a=document.createElement("a");a.href=r,a.download=`audit-trace-${p}-${S}-${(new Date).toISOString().split("T")[0]}.csv`,document.body.appendChild(a),a.click(),document.body.removeChild(a),URL.revokeObjectURL(r),B.success(A("audit.exportSuccess",{format:"CSV"}))},"data-testid":"audit-trace-export-csv"},{key:"json",label:A("audit.exportJSON"),icon:e.jsx(v,{}),onClick:()=>{if(!H?.records||0===H.records.length)return;const e={entityType:p,entityIdentifier:S,entityName:M,exportDate:(new Date).toISOString(),summary:H.summary,records:H.records.map(e=>({actionType:e.actionType,details:e.details,performedBy:e.performedBy||"System",timestamp:e.timestamp,timeAgo:e.timeAgo,iconHint:e.iconHint}))},t=JSON.stringify(e,null,2),r=new Blob([t],{type:"application/json"}),a=URL.createObjectURL(r),s=document.createElement("a");s.href=a,s.download=`audit-trace-${p}-${S}-${(new Date).toISOString().split("T")[0]}.json`,document.body.appendChild(s),s.click(),document.body.removeChild(s),URL.revokeObjectURL(a),B.success(A("audit.exportSuccess",{format:"JSON"}))},"data-testid":"audit-trace-export-json"}]},placement:"bottomRight","data-testid":"audit-trace-export-dropdown",children:e.jsx(C,{icon:e.jsx(y,{}),"data-testid":"audit-trace-export-button",style:I.buttonSecondary,children:A("audit.export")})})]})}),e.jsx(R,{columns:X,dataSource:H.records,rowKey:(e,t)=>`${e.timestamp}-${t}`,pagination:{pageSize:10,showSizeChanger:!1,showTotal:(e,t)=>A("common:general.showingRecords",{start:t[0],end:t[1],total:e})},scroll:{x:800},size:"small","data-testid":"audit-trace-table"})]}):null})};export{oe as A};
