import{j as e}from"./chunk-DUi8bg1D.js";import{r as t,d as r,m as a,a1 as s,p as o,L as i,H as n,a3 as c,g as d,e as l,aK as u,ab as m,bp as p,q as h}from"../index-DldRJJRQ.js";import{r as f,g as x}from"./chunk-DDwtzQW6.js";import{E as j}from"./chunk-DzCZ8c5k.js";import{D as y}from"./chunk-GYFfhnqx.js";import{C as g}from"./chunk-CY4jNBZn.js";import{D as v}from"./chunk-Dc77jU8D.js";import{C as b}from"./chunk-Dv8HU_HO.js";import{H as $}from"./chunk-DlialLHl.js";import{F as k}from"./chunk-wbuWZ0uz.js";import{F as w}from"./chunk-CushYHaH.js";import{b as O}from"./chunk-DeSLytzZ.js";import"./chunk-BdxPdFN0.js";import{f as S}from"./chunk-DhpoEw86.js";import{c as L,d as D}from"./chunk-BKxNWyZX.js";import{M as _,S as M,d as T,T as C,A as R,k as I,c as A,F as B,u as P}from"./chunk-CX_EivFx.js";import{a as z}from"./chunk-5z2yL1vW.js";import{u as H}from"./chunk-BQNjmpVv.js";import"./chunk-DB6ez0TU.js";var U,E,N,X={exports:{}},V={},W={};function F(){if(U)return W;U=1,Object.defineProperty(W,"__esModule",{value:!0});return W.default={icon:{tag:"svg",attrs:{viewBox:"64 64 896 896",focusable:"false"},children:[{tag:"path",attrs:{d:"M696 480H544V328c0-4.4-3.6-8-8-8h-48c-4.4 0-8 3.6-8 8v152H328c-4.4 0-8 3.6-8 8v48c0 4.4 3.6 8 8 8h152v152c0 4.4 3.6 8 8 8h48c4.4 0 8-3.6 8-8V544h152c4.4 0 8-3.6 8-8v-48c0-4.4-3.6-8-8-8z"}},{tag:"path",attrs:{d:"M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm0 820c-205.4 0-372-166.6-372-372s166.6-372 372-372 372 166.6 372 372-166.6 372-372 372z"}}]},name:"plus-circle",theme:"outlined"},W}function G(){if(E)return V;E=1,Object.defineProperty(V,"__esModule",{value:!0}),V.default=void 0;var e=function(e,t){if(e&&e.__esModule)return e;if(null===e||"object"!=typeof e&&"function"!=typeof e)return{default:e};var r=o(t);if(r&&r.has(e))return r.get(e);var a={__proto__:null},s=Object.defineProperty&&Object.getOwnPropertyDescriptor;for(var i in e)if("default"!==i&&Object.prototype.hasOwnProperty.call(e,i)){var n=s?Object.getOwnPropertyDescriptor(e,i):null;n&&(n.get||n.set)?Object.defineProperty(a,i,n):a[i]=e[i]}return a.default=e,r&&r.set(e,a),a}(f()),r=s(F()),a=s(t());function s(e){return e&&e.__esModule?e:{default:e}}function o(e){if("function"!=typeof WeakMap)return null;var t=new WeakMap,r=new WeakMap;return(o=function(e){return e?r:t})(e)}function i(){return i=Object.assign?Object.assign.bind():function(e){for(var t=1;t<arguments.length;t++){var r=arguments[t];for(var a in r)Object.prototype.hasOwnProperty.call(r,a)&&(e[a]=r[a])}return e},i.apply(this,arguments)}const n=(t,s)=>e.createElement(a.default,i({},t,{ref:s,icon:r.default})),c=e.forwardRef(n);return V.default=c,V}function J(){return N||(N=1,function(e,t){Object.defineProperty(t,"__esModule",{value:!0}),t.default=void 0;var r;const a=(r=G())&&r.__esModule?r:{default:r};t.default=a,e.exports=a}(X,X.exports)),X.exports}const K=x(J()),Y=a`
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
`,q=r(_)`
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
`,Z=r.div`
  text-align: center;
  padding: ${({theme:e})=>e.spacing.XXXL}px 0;
`,Q=r.div`
  margin-top: ${({theme:e})=>e.spacing.MD}px;
  color: ${({theme:e})=>e.colors.textSecondary};
`,ee=r.div`
  width: 100%;
  margin-bottom: ${({theme:e})=>e.spacing.LG}px;
`,te=r.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
`,re=r.div`
  display: flex;
  gap: ${({theme:e})=>e.spacing.XL}px;
`,ae=r.div`
  display: flex;
  flex-direction: column;
  gap: 0;
`,se=r.span`
  font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
  font-size: ${({theme:e})=>e.fontSize.XL}px;
`,{Text:oe}=C,ie=({open:t,onCancel:r,entityType:a,entityIdentifier:f,entityName:x})=>{const{t:_}=H(["resources","common"]),C=z(),{data:U,isLoading:E,error:N}=O(a,f,t),X=t=>{const r="var(--color-error)",a="var(--color-text-secondary)";switch(t){case"plus-circle":return e.jsx(c,{$color:a,children:e.jsx(K,{})});case"edit":return e.jsx(c,{$color:a,children:e.jsx(j,{})});case"trash":return e.jsx(c,{$color:r,children:e.jsx(h,{})});case"lock":return e.jsx(c,{$color:a,children:e.jsx(p,{})});case"key":return e.jsx(c,{$color:a,children:e.jsx(m,{})});case"users":return e.jsx(c,{$color:a,children:e.jsx(u,{})});case"check-circle":return e.jsx(c,{$color:a,children:e.jsx(l,{})});case"x-circle":return e.jsx(c,{$color:r,children:e.jsx(b,{})});case"database":return e.jsx(c,{$color:a,children:e.jsx(y,{})});case"hdd":return e.jsx(c,{$color:a,children:e.jsx($,{})});case"copy":return e.jsx(c,{$color:a,children:e.jsx(g,{})});default:return e.jsx(c,{$color:a,children:e.jsx(d,{})})}},V=e=>{switch(e){case"Deleted":case"Cancelled":return"error";default:return"default"}},W=[{title:_("audit.action"),key:"action",width:150,sorter:L("actionType"),render:(t,r,a)=>e.jsxs(M,{"data-testid":`audit-trace-action-${a}`,children:[X(r.iconHint),e.jsx(T,{color:V(r.actionType),"data-testid":`audit-trace-action-tag-${a}`,children:r.actionType})]})},{title:_("audit.details"),dataIndex:"details",key:"details",ellipsis:!0,sorter:L("details")},{title:_("audit.performedBy"),dataIndex:"performedBy",key:"performedBy",width:200,sorter:L("performedBy"),render:(t,r,a)=>e.jsx("span",{"data-testid":`audit-trace-performed-by-${a}`,children:t||_("audit.system")})},{title:_("audit.timestamp"),dataIndex:"timestamp",key:"timestamp",width:200,sorter:D("timestamp"),render:(t,r,a)=>e.jsxs(M,{orientation:"vertical",size:0,"data-testid":`audit-trace-timestamp-${a}`,children:[e.jsx(oe,{children:S(t,"datetime")}),e.jsx(s,{$muted:!0,children:r.timeAgo})]})}];return e.jsx(q,{title:e.jsxs(M,{children:[e.jsx(n,{}),_("audit.title",{name:x||f})]}),open:t,onCancel:r,width:o.DIMENSIONS.MODAL_WIDTH_XL,footer:null,destroyOnHidden:!0,"data-testid":"audit-trace-modal",children:E?e.jsxs(Z,{"data-testid":"audit-trace-loading",children:[e.jsx(i,{loading:!0,centered:!0,minHeight:160,children:e.jsx("div",{})}),e.jsx(Q,{children:_("common:general.loading")})]}):N?e.jsx(R,{message:_("audit.error"),description:N instanceof Error?N.message:_("audit.errorLoading"),type:"error",showIcon:!0,"data-testid":"audit-trace-error-alert"}):U?e.jsxs(e.Fragment,{children:[U.summary&&e.jsx(ee,{"data-testid":"audit-trace-summary",children:e.jsxs(te,{children:[e.jsxs(re,{children:[e.jsxs(ae,{"data-testid":"audit-trace-total-records",children:[e.jsx(oe,{type:"secondary",children:_("audit.totalRecords")}),e.jsx(se,{children:U.summary.totalAuditRecords})]}),e.jsxs(ae,{"data-testid":"audit-trace-visible-records",children:[e.jsx(oe,{type:"secondary",children:_("audit.visibleRecords")}),e.jsx(se,{children:U.summary.visibleAuditRecords})]}),U.summary.lastActivity&&e.jsxs(ae,{"data-testid":"audit-trace-last-activity",children:[e.jsx(oe,{type:"secondary",children:_("audit.lastActivity")}),e.jsx(oe,{strong:!0,children:new Date(U.summary.lastActivity).toLocaleDateString()})]})]}),e.jsx(I,{menu:{items:[{key:"csv",label:_("audit.exportCSV"),icon:e.jsx(w,{}),onClick:()=>{if(!U?.records||0===U.records.length)return;const e=[["Action","Details","Performed By","Timestamp","Time Ago"].join(","),...U.records.map(e=>[e.actionType,`"${e.details.replace(/"/g,'""')}"`,e.performedBy||"System",S(e.timestamp,"datetime"),e.timeAgo].join(","))].join("\n"),t=new Blob([e],{type:"text/csv;charset=utf-8;"}),r=URL.createObjectURL(t),s=document.createElement("a");s.href=r,s.download=`audit-trace-${a}-${f}-${(new Date).toISOString().split("T")[0]}.csv`,document.body.appendChild(s),s.click(),document.body.removeChild(s),URL.revokeObjectURL(r),P.success(_("audit.exportSuccess",{format:"CSV"}))},"data-testid":"audit-trace-export-csv"},{key:"json",label:_("audit.exportJSON"),icon:e.jsx(k,{}),onClick:()=>{if(!U?.records||0===U.records.length)return;const e={entityType:a,entityIdentifier:f,entityName:x,exportDate:(new Date).toISOString(),summary:U.summary,records:U.records.map(e=>({actionType:e.actionType,details:e.details,performedBy:e.performedBy||"System",timestamp:e.timestamp,timeAgo:e.timeAgo,iconHint:e.iconHint}))},t=JSON.stringify(e,null,2),r=new Blob([t],{type:"application/json"}),s=URL.createObjectURL(r),o=document.createElement("a");o.href=s,o.download=`audit-trace-${a}-${f}-${(new Date).toISOString().split("T")[0]}.json`,document.body.appendChild(o),o.click(),document.body.removeChild(o),URL.revokeObjectURL(s),P.success(_("audit.exportSuccess",{format:"JSON"}))},"data-testid":"audit-trace-export-json"}]},placement:"bottomRight","data-testid":"audit-trace-export-dropdown",children:e.jsx(A,{icon:e.jsx(v,{}),"data-testid":"audit-trace-export-button",style:C.buttonSecondary,children:_("audit.export")})})]})}),e.jsx(B,{columns:W,dataSource:U.records,rowKey:(e,t)=>`${e.timestamp}-${t}`,pagination:{pageSize:10,showSizeChanger:!1,showTotal:(e,t)=>_("common:general.showingRecords",{start:t[0],end:t[1],total:e})},scroll:{x:800},size:"small","data-testid":"audit-trace-table"})]}):null})};export{ie as default};
