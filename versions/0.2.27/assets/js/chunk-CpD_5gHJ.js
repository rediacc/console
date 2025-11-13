import{j as e}from"./chunk-I_umDLoV.js";import{r as t,u as r,h as a,c as s,d as o,H as i,b as n,U as c,K as d,O as l,k as u}from"../index-CqYCcjHh.js";import{f as m,g as p}from"./chunk-DaihG_v-.js";import{b as f,E as h}from"./chunk-C7kzYpYI.js";import{C as x,D as j}from"./chunk-BQhl7Jz1.js";import{D as y}from"./chunk-arvZhiB1.js";import{C as g}from"./chunk-h5BPjb58.js";import{F as v}from"./chunk-CNk50oxw.js";import{F as b}from"./chunk-x6B2F5p0.js";import{f as $}from"./chunk-DVhBN_BK.js";import{d as w,q as S}from"./chunk-VAXc7D1f.js";import{M as k,a as O,e as C,T as D,n as L,g as M,D as R,B as _,w as A,s as I}from"./chunk-DxOBGMQf.js";import{u as T}from"./chunk-DfOmacDz.js";var B,z,P,U={exports:{}},H={},E={};function N(){if(B)return E;B=1,Object.defineProperty(E,"__esModule",{value:!0});return E.default={icon:{tag:"svg",attrs:{viewBox:"64 64 896 896",focusable:"false"},children:[{tag:"path",attrs:{d:"M696 480H544V328c0-4.4-3.6-8-8-8h-48c-4.4 0-8 3.6-8 8v152H328c-4.4 0-8 3.6-8 8v48c0 4.4 3.6 8 8 8h152v152c0 4.4 3.6 8 8 8h48c4.4 0 8-3.6 8-8V544h152c4.4 0 8-3.6 8-8v-48c0-4.4-3.6-8-8-8z"}},{tag:"path",attrs:{d:"M512 64C264.6 64 64 264.6 64 512s200.6 448 448 448 448-200.6 448-448S759.4 64 512 64zm0 820c-205.4 0-372-166.6-372-372s166.6-372 372-372 372 166.6 372 372-166.6 372-372 372z"}}]},name:"plus-circle",theme:"outlined"},E}function X(){if(z)return H;z=1,Object.defineProperty(H,"__esModule",{value:!0}),H.default=void 0;var e=function(e,t){if(e&&e.__esModule)return e;if(null===e||"object"!=typeof e&&"function"!=typeof e)return{default:e};var r=o(t);if(r&&r.has(e))return r.get(e);var a={__proto__:null},s=Object.defineProperty&&Object.getOwnPropertyDescriptor;for(var i in e)if("default"!==i&&Object.prototype.hasOwnProperty.call(e,i)){var n=s?Object.getOwnPropertyDescriptor(e,i):null;n&&(n.get||n.set)?Object.defineProperty(a,i,n):a[i]=e[i]}return a.default=e,r&&r.set(e,a),a}(m()),r=s(N()),a=s(t());function s(e){return e&&e.__esModule?e:{default:e}}function o(e){if("function"!=typeof WeakMap)return null;var t=new WeakMap,r=new WeakMap;return(o=function(e){return e?r:t})(e)}function i(){return i=Object.assign?Object.assign.bind():function(e){for(var t=1;t<arguments.length;t++){var r=arguments[t];for(var a in r)Object.prototype.hasOwnProperty.call(r,a)&&(e[a]=r[a])}return e},i.apply(this,arguments)}const n=(t,s)=>e.createElement(a.default,i({},t,{ref:s,icon:r.default})),c=e.forwardRef(n);return H.default=c,H}function W(){return P||(P=1,function(e,t){Object.defineProperty(t,"__esModule",{value:!0}),t.default=void 0;var r;const a=(r=X())&&r.__esModule?r:{default:r};t.default=a,e.exports=a}(U,U.exports)),U.exports}const G=p(W()),J=S`
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
`,V=w(k)`
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
`,F=w.div`
  text-align: center;
  padding: ${({theme:e})=>e.spacing.XXXL}px 0;
`,K=w.div`
  margin-top: ${({theme:e})=>e.spacing.MD}px;
  color: ${({theme:e})=>e.colors.textSecondary};
`,Y=w.div`
  width: 100%;
  margin-bottom: ${({theme:e})=>e.spacing.LG}px;
`,q=w.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
`,Q=w.div`
  display: flex;
  gap: ${({theme:e})=>e.spacing.XL}px;
`,Z=w.div`
  display: flex;
  flex-direction: column;
  gap: 0;
`,ee=w.span`
  font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
  font-size: ${({theme:e})=>e.fontSize.XL}px;
`,te=w.span`
  color: ${({$color:e})=>e};
`,{Text:re}=D,ae=({open:t,onCancel:m,entityType:p,entityIdentifier:w,entityName:S})=>{const{t:k}=T(["resources","common"]),D=r(),{data:B,isLoading:z,error:P}=f(p,w,t),U=t=>{switch(t){case"plus-circle":return e.jsx(te,{$color:"#52c41a",children:e.jsx(G,{})});case"edit":return e.jsx(te,{$color:"#1890ff",children:e.jsx(h,{})});case"trash":return e.jsx(te,{$color:"#ff4d4f",children:e.jsx(u,{})});case"lock":return e.jsx(te,{$color:"#fa8c16",children:e.jsx(l,{})});case"key":return e.jsx(te,{$color:"#722ed1",children:e.jsx(d,{})});case"users":return e.jsx(te,{$color:"#13c2c2",children:e.jsx(c,{})});case"check-circle":return e.jsx(te,{$color:"#52c41a",children:e.jsx(n,{})});case"x-circle":return e.jsx(te,{$color:"#ff4d4f",children:e.jsx(g,{})});case"database":return e.jsx(te,{$color:"#1890ff",children:e.jsx(j,{})});case"hdd":return e.jsx(te,{$color:"#fa8c16",children:e.jsx(i,{})});case"copy":return e.jsx(te,{$color:"#722ed1",children:e.jsx(x,{})});default:return e.jsx(te,{$color:"#1890ff",children:e.jsx(o,{})})}},H=e=>{switch(e){case"Created":return"green";case"Updated":case"Renamed":case"Assigned to Cluster":case"Assigned to Image":case"Assigned to Clone":return"blue";case"Deleted":return"red";case"Activated":return"cyan";case"Deactivated":case"Removed from Cluster":case"Removed from Clone":return"orange";case"Security Update":case"Security Setting":return"gold";case"Completed":return"success";case"Cancelled":return"error";case"Reassigned Image":return"purple";default:return"default"}},E=[{title:k("audit.action"),key:"action",width:150,render:(t,r,a)=>e.jsxs(O,{"data-testid":`audit-trace-action-${a}`,children:[U(r.iconHint),e.jsx(C,{color:H(r.actionType),"data-testid":`audit-trace-action-tag-${a}`,children:r.actionType})]})},{title:k("audit.details"),dataIndex:"details",key:"details",ellipsis:!0},{title:k("audit.performedBy"),dataIndex:"performedBy",key:"performedBy",width:200,render:(t,r,a)=>e.jsx("span",{"data-testid":`audit-trace-performed-by-${a}`,children:t||k("audit.system")})},{title:k("audit.timestamp"),dataIndex:"timestamp",key:"timestamp",width:200,render:(t,r,a)=>e.jsxs(O,{direction:"vertical",size:0,"data-testid":`audit-trace-timestamp-${a}`,children:[e.jsx(re,{children:$(t,"datetime")}),e.jsx(re,{type:"secondary",style:{fontSize:12},children:r.timeAgo})]})}];return e.jsx(V,{title:e.jsxs(O,{children:[e.jsx(s,{}),k("audit.title",{name:S||w})]}),open:t,onCancel:m,width:a.DIMENSIONS.MODAL_WIDTH_XL,footer:null,destroyOnHidden:!0,"data-testid":"audit-trace-modal",children:z?e.jsxs(F,{"data-testid":"audit-trace-loading",children:[e.jsx(L,{size:"large"}),e.jsx(K,{children:k("common:general.loading")})]}):P?e.jsx(M,{message:k("audit.error"),description:P instanceof Error?P.message:k("audit.errorLoading"),type:"error",showIcon:!0,"data-testid":"audit-trace-error-alert"}):B?e.jsxs(e.Fragment,{children:[B.summary&&e.jsx(Y,{"data-testid":"audit-trace-summary",children:e.jsxs(q,{children:[e.jsxs(Q,{children:[e.jsxs(Z,{"data-testid":"audit-trace-total-records",children:[e.jsx(re,{type:"secondary",children:k("audit.totalRecords")}),e.jsx(ee,{children:B.summary.totalAuditRecords})]}),e.jsxs(Z,{"data-testid":"audit-trace-visible-records",children:[e.jsx(re,{type:"secondary",children:k("audit.visibleRecords")}),e.jsx(ee,{children:B.summary.visibleAuditRecords})]}),B.summary.lastActivity&&e.jsxs(Z,{"data-testid":"audit-trace-last-activity",children:[e.jsx(re,{type:"secondary",children:k("audit.lastActivity")}),e.jsx(re,{strong:!0,children:new Date(B.summary.lastActivity).toLocaleDateString()})]})]}),e.jsx(R,{menu:{items:[{key:"csv",label:k("audit.exportCSV"),icon:e.jsx(b,{}),onClick:()=>{if(!B?.records||0===B.records.length)return;const e=[["Action","Details","Performed By","Timestamp","Time Ago"].join(","),...B.records.map(e=>[e.actionType,`"${e.details.replace(/"/g,'""')}"`,e.performedBy||"System",$(e.timestamp,"datetime"),e.timeAgo].join(","))].join("\n"),t=new Blob([e],{type:"text/csv;charset=utf-8;"}),r=URL.createObjectURL(t),a=document.createElement("a");a.href=r,a.download=`audit-trace-${p}-${w}-${(new Date).toISOString().split("T")[0]}.csv`,document.body.appendChild(a),a.click(),document.body.removeChild(a),URL.revokeObjectURL(r),I.success(k("audit.exportSuccess",{format:"CSV"}))},"data-testid":"audit-trace-export-csv"},{key:"json",label:k("audit.exportJSON"),icon:e.jsx(v,{}),onClick:()=>{if(!B?.records||0===B.records.length)return;const e={entityType:p,entityIdentifier:w,entityName:S,exportDate:(new Date).toISOString(),summary:B.summary,records:B.records.map(e=>({actionType:e.actionType,details:e.details,performedBy:e.performedBy||"System",timestamp:e.timestamp,timeAgo:e.timeAgo,iconHint:e.iconHint}))},t=JSON.stringify(e,null,2),r=new Blob([t],{type:"application/json"}),a=URL.createObjectURL(r),s=document.createElement("a");s.href=a,s.download=`audit-trace-${p}-${w}-${(new Date).toISOString().split("T")[0]}.json`,document.body.appendChild(s),s.click(),document.body.removeChild(s),URL.revokeObjectURL(a),I.success(k("audit.exportSuccess",{format:"JSON"}))},"data-testid":"audit-trace-export-json"}]},placement:"bottomRight","data-testid":"audit-trace-export-dropdown",children:e.jsx(_,{icon:e.jsx(y,{}),"data-testid":"audit-trace-export-button",style:D.buttonSecondary,children:k("audit.export")})})]})}),e.jsx(A,{columns:E,dataSource:B.records,rowKey:(e,t)=>`${e.timestamp}-${t}`,pagination:{pageSize:10,showSizeChanger:!1,showTotal:(e,t)=>k("common:general.showingRecords",{start:t[0],end:t[1],total:e})},scroll:{x:800},size:"small","data-testid":"audit-trace-table"})]}):null})};export{ae as A};
