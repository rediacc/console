import{j as e}from"./chunk-jIVxg-O4.js";import{r as t,u as r,i as a,H as s,d as o,c as i,X as n,K as c,al as d,j as l}from"../index-BVsYfcoL.js";import{f as u,g as m}from"./chunk-DaihG_v-.js";import{f as p,c as h,d as f,E as x}from"./chunk-DFYzG_vc.js";import{H as j,D as y}from"./chunk-5sosBwx6.js";import{C as g}from"./chunk-B9exjbYy.js";import{D as v}from"./chunk-BDNxzjFo.js";import{C as b}from"./chunk-Js6vx5XE.js";import{F as $}from"./chunk-DaXCINTh.js";import{F as k}from"./chunk-BpQPiMEo.js";import{f as w}from"./chunk-DVhBN_BK.js";import{d as O,m as S}from"./chunk-CsUqxJyM.js";import{M as L,c as D,a as _,T as M,q as T,h as C,D as R,B as A,F as B,s as I}from"./chunk-DcGI-zRP.js";import{u as z}from"./chunk-DfOmacDz.js";var P,H,U,X={exports:{}},E={},N={};function V(){if(P)return N;P=1,Object.defineProperty(N,"__esModule",{value:!0});return N.default={icon:{tag:"svg",attrs:{viewBox:"64 64 896 896",focusable:"false"},children:[{tag:"path",attrs:{d:"M696 480H544V328c0-4.4-3.6-8-8-8h-48c-4.4 0-8 3.6-8 8v152H328c-4.4 0-8 3.6-8 8v48c0 4.4 3.6 8 8 8h152v152c0 4.4 3.6 8 8 8h48c4.4 0 8-3.6 8-8V544h152c4.4 0 8-3.6 8-8v-48c0-4.4-3.6-8-8-8z"}},{tag:"path",attrs:{d:"M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm0 820c-205.4 0-372-166.6-372-372s166.6-372 372-372 372 166.6 372 372-166.6 372-372 372z"}}]},name:"plus-circle",theme:"outlined"},N}function W(){if(H)return E;H=1,Object.defineProperty(E,"__esModule",{value:!0}),E.default=void 0;var e=function(e,t){if(e&&e.__esModule)return e;if(null===e||"object"!=typeof e&&"function"!=typeof e)return{default:e};var r=o(t);if(r&&r.has(e))return r.get(e);var a={__proto__:null},s=Object.defineProperty&&Object.getOwnPropertyDescriptor;for(var i in e)if("default"!==i&&Object.prototype.hasOwnProperty.call(e,i)){var n=s?Object.getOwnPropertyDescriptor(e,i):null;n&&(n.get||n.set)?Object.defineProperty(a,i,n):a[i]=e[i]}return a.default=e,r&&r.set(e,a),a}(u()),r=s(V()),a=s(t());function s(e){return e&&e.__esModule?e:{default:e}}function o(e){if("function"!=typeof WeakMap)return null;var t=new WeakMap,r=new WeakMap;return(o=function(e){return e?r:t})(e)}function i(){return i=Object.assign?Object.assign.bind():function(e){for(var t=1;t<arguments.length;t++){var r=arguments[t];for(var a in r)Object.prototype.hasOwnProperty.call(r,a)&&(e[a]=r[a])}return e},i.apply(this,arguments)}const n=(t,s)=>e.createElement(a.default,i({},t,{ref:s,icon:r.default})),c=e.forwardRef(n);return E.default=c,E}function F(){return U||(U=1,function(e,t){Object.defineProperty(t,"__esModule",{value:!0}),t.default=void 0;var r;const a=(r=W())&&r.__esModule?r:{default:r};t.default=a,e.exports=a}(X,X.exports)),X.exports}const G=m(F()),J=S`
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
`,q=O(L)`
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
`,K=O.div`
  text-align: center;
  padding: ${({theme:e})=>e.spacing.XXXL}px 0;
`,Y=O.div`
  margin-top: ${({theme:e})=>e.spacing.MD}px;
  color: ${({theme:e})=>e.colors.textSecondary};
`,Q=O.div`
  width: 100%;
  margin-bottom: ${({theme:e})=>e.spacing.LG}px;
`,Z=O.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
`,ee=O.div`
  display: flex;
  gap: ${({theme:e})=>e.spacing.XL}px;
`,te=O.div`
  display: flex;
  flex-direction: column;
  gap: 0;
`,re=O.span`
  font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
  font-size: ${({theme:e})=>e.fontSize.XL}px;
`,ae=O.span`
  color: ${({$color:e})=>e};
`,{Text:se}=M,oe=({open:t,onCancel:u,entityType:m,entityIdentifier:O,entityName:S})=>{const{t:L}=z(["resources","common"]),M=r(),{data:P,isLoading:H,error:U}=p(m,O,t),X=t=>{const r="var(--color-error)",a="var(--color-text-secondary)";switch(t){case"plus-circle":return e.jsx(ae,{$color:a,children:e.jsx(G,{})});case"edit":return e.jsx(ae,{$color:a,children:e.jsx(x,{})});case"trash":return e.jsx(ae,{$color:r,children:e.jsx(l,{})});case"lock":return e.jsx(ae,{$color:a,children:e.jsx(d,{})});case"key":return e.jsx(ae,{$color:a,children:e.jsx(c,{})});case"users":return e.jsx(ae,{$color:a,children:e.jsx(n,{})});case"check-circle":return e.jsx(ae,{$color:a,children:e.jsx(i,{})});case"x-circle":return e.jsx(ae,{$color:r,children:e.jsx(b,{})});case"database":return e.jsx(ae,{$color:a,children:e.jsx(y,{})});case"hdd":return e.jsx(ae,{$color:a,children:e.jsx(j,{})});case"copy":return e.jsx(ae,{$color:a,children:e.jsx(g,{})});default:return e.jsx(ae,{$color:a,children:e.jsx(o,{})})}},E=e=>{switch(e){case"Deleted":case"Cancelled":return"error";default:return"default"}},N=[{title:L("audit.action"),key:"action",width:150,sorter:h("actionType"),render:(t,r,a)=>e.jsxs(D,{"data-testid":`audit-trace-action-${a}`,children:[X(r.iconHint),e.jsx(_,{color:E(r.actionType),"data-testid":`audit-trace-action-tag-${a}`,children:r.actionType})]})},{title:L("audit.details"),dataIndex:"details",key:"details",ellipsis:!0,sorter:h("details")},{title:L("audit.performedBy"),dataIndex:"performedBy",key:"performedBy",width:200,sorter:h("performedBy"),render:(t,r,a)=>e.jsx("span",{"data-testid":`audit-trace-performed-by-${a}`,children:t||L("audit.system")})},{title:L("audit.timestamp"),dataIndex:"timestamp",key:"timestamp",width:200,sorter:f("timestamp"),render:(t,r,a)=>e.jsxs(D,{direction:"vertical",size:0,"data-testid":`audit-trace-timestamp-${a}`,children:[e.jsx(se,{children:w(t,"datetime")}),e.jsx(se,{type:"secondary",style:{fontSize:12},children:r.timeAgo})]})}];return e.jsx(q,{title:e.jsxs(D,{children:[e.jsx(s,{}),L("audit.title",{name:S||O})]}),open:t,onCancel:u,width:a.DIMENSIONS.MODAL_WIDTH_XL,footer:null,destroyOnHidden:!0,"data-testid":"audit-trace-modal",children:H?e.jsxs(K,{"data-testid":"audit-trace-loading",children:[e.jsx(T,{size:"large"}),e.jsx(Y,{children:L("common:general.loading")})]}):U?e.jsx(C,{message:L("audit.error"),description:U instanceof Error?U.message:L("audit.errorLoading"),type:"error",showIcon:!0,"data-testid":"audit-trace-error-alert"}):P?e.jsxs(e.Fragment,{children:[P.summary&&e.jsx(Q,{"data-testid":"audit-trace-summary",children:e.jsxs(Z,{children:[e.jsxs(ee,{children:[e.jsxs(te,{"data-testid":"audit-trace-total-records",children:[e.jsx(se,{type:"secondary",children:L("audit.totalRecords")}),e.jsx(re,{children:P.summary.totalAuditRecords})]}),e.jsxs(te,{"data-testid":"audit-trace-visible-records",children:[e.jsx(se,{type:"secondary",children:L("audit.visibleRecords")}),e.jsx(re,{children:P.summary.visibleAuditRecords})]}),P.summary.lastActivity&&e.jsxs(te,{"data-testid":"audit-trace-last-activity",children:[e.jsx(se,{type:"secondary",children:L("audit.lastActivity")}),e.jsx(se,{strong:!0,children:new Date(P.summary.lastActivity).toLocaleDateString()})]})]}),e.jsx(R,{menu:{items:[{key:"csv",label:L("audit.exportCSV"),icon:e.jsx(k,{}),onClick:()=>{if(!P?.records||0===P.records.length)return;const e=[["Action","Details","Performed By","Timestamp","Time Ago"].join(","),...P.records.map(e=>[e.actionType,`"${e.details.replace(/"/g,'""')}"`,e.performedBy||"System",w(e.timestamp,"datetime"),e.timeAgo].join(","))].join("\n"),t=new Blob([e],{type:"text/csv;charset=utf-8;"}),r=URL.createObjectURL(t),a=document.createElement("a");a.href=r,a.download=`audit-trace-${m}-${O}-${(new Date).toISOString().split("T")[0]}.csv`,document.body.appendChild(a),a.click(),document.body.removeChild(a),URL.revokeObjectURL(r),I.success(L("audit.exportSuccess",{format:"CSV"}))},"data-testid":"audit-trace-export-csv"},{key:"json",label:L("audit.exportJSON"),icon:e.jsx($,{}),onClick:()=>{if(!P?.records||0===P.records.length)return;const e={entityType:m,entityIdentifier:O,entityName:S,exportDate:(new Date).toISOString(),summary:P.summary,records:P.records.map(e=>({actionType:e.actionType,details:e.details,performedBy:e.performedBy||"System",timestamp:e.timestamp,timeAgo:e.timeAgo,iconHint:e.iconHint}))},t=JSON.stringify(e,null,2),r=new Blob([t],{type:"application/json"}),a=URL.createObjectURL(r),s=document.createElement("a");s.href=a,s.download=`audit-trace-${m}-${O}-${(new Date).toISOString().split("T")[0]}.json`,document.body.appendChild(s),s.click(),document.body.removeChild(s),URL.revokeObjectURL(a),I.success(L("audit.exportSuccess",{format:"JSON"}))},"data-testid":"audit-trace-export-json"}]},placement:"bottomRight","data-testid":"audit-trace-export-dropdown",children:e.jsx(A,{icon:e.jsx(v,{}),"data-testid":"audit-trace-export-button",style:M.buttonSecondary,children:L("audit.export")})})]})}),e.jsx(B,{columns:N,dataSource:P.records,rowKey:(e,t)=>`${e.timestamp}-${t}`,pagination:{pageSize:10,showSizeChanger:!1,showTotal:(e,t)=>L("common:general.showingRecords",{start:t[0],end:t[1],total:e})},scroll:{x:800},size:"small","data-testid":"audit-trace-table"})]}):null})};export{oe as A};
