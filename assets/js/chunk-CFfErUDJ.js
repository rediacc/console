import{j as e}from"./chunk-jIVxg-O4.js";import{q as t}from"../index-pYX32kNS.js";import{S as i}from"./chunk-B5MW1YpM.js";import{R as a}from"./chunk-C1ix3zog.js";import{d as r,a as s}from"./chunk-CsUqxJyM.js";import{I as n,T as o,C as l,c,B as d,q as p,E as h,l as m,F as x}from"./chunk-DcGI-zRP.js";const{Text:g}=o,f=r(l)`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.XL}px;
    border-color: ${({theme:e})=>e.colors.borderSecondary};
    box-shadow: ${({theme:e})=>e.shadows.CARD};
    background-color: ${({theme:e})=>e.colors.bgPrimary};
  }
`,u=r.div`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
`,w=r.div`
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.MD}px;

  @media (max-width: 768px) {
    flex-direction: column;
    align-items: stretch;
  }
`,j=r.div`
  display: flex;
  flex: 1 1 auto;
  min-width: 0;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.MD}px;

  @media (max-width: 768px) {
    flex-direction: column;
    align-items: stretch;
    width: 100%;
  }
`,$=r.div`
  display: flex;
  align-items: center;
`,y=r.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({theme:e})=>e.spacing.SM}px;

  @media (max-width: 768px) {
    width: 100%;
    justify-content: flex-end;
  }
`,S=r(n.Search)`
  && {
    width: 300px;
    min-height: ${({theme:e})=>e.dimensions.INPUT_HEIGHT}px;
    border-radius: ${({theme:e})=>e.borderRadius.LG}px;
  }

  @media (max-width: 768px) {
    && {
      width: 100%;
    }
  }
`,b=r.div`
  text-align: center;
  padding: ${({theme:e})=>e.spacing.XXXXL}px 0;
`,v=r(c).attrs({direction:"vertical",align:"center",size:"middle"})`
  text-align: center;
  padding: ${({theme:e})=>e.spacing.LG}px;
`,R=r(g)`
  && {
    color: ${({theme:e})=>e.colors.textPrimary};
    font-size: ${({theme:e})=>e.fontSize.BASE}px;
  }
`,T=r(g)`
  && {
    font-size: ${({theme:e})=>e.fontSize.SM}px;
    color: ${({theme:e})=>e.colors.textSecondary};
  }
`,k=r(c).attrs({size:"small"})`
  display: flex;
  justify-content: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,z=s`
  min-height: ${({theme:e})=>e.dimensions.INPUT_HEIGHT}px;
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
`,C=r(d)`
  && {
    ${z};
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
`,E=r(d)`
  && {
    ${z};
  }
`,M=r.div`
  /* Better scroll experience on mobile devices */
  @media (max-width: 576px) {
    -webkit-overflow-scrolling: touch;
    
    .ant-table-wrapper {
      overflow-x: auto;
    }
    
    .ant-table-pagination {
      flex-wrap: wrap;
      justify-content: center;
      gap: ${({theme:e})=>e.spacing.SM}px;
      
      .ant-pagination-total-text {
        flex-basis: 100%;
        text-align: center;
        margin-bottom: ${({theme:e})=>e.spacing.XS}px;
      }
    }
  }

  /* Shrink the select in pagination */
  .ant-pagination-options {
    .ant-select {
      .ant-select-selector {
        height: 32px !important;
        min-height: 32px !important;
        padding: 0 32px 0 12px !important; /* Space for arrow on right, text on left */
      }
      
      .ant-select-selection-item {
        line-height: 30px !important;
        padding-right: 0 !important;
      }
      
      .ant-select-arrow {
        top: 50% !important;
        transform: translateY(-50%) !important;
        right: 6px !important;
      }
    }
  }
`;function P({title:r,loading:s=!1,data:n=[],columns:o,searchPlaceholder:l="Search...",onSearch:c,filters:d,actions:g,rowKey:z="id",emptyText:P="No data available",pagination:G,onRow:I,rowSelection:N,onCreateNew:D,onRefresh:L,createButtonText:X="Create New",emptyDescription:B,resourceType:H="items"}){const _=Boolean(r||c||d||g),A=B||P,q=H&&H.endsWith("s")?H.slice(0,-1):H,K=!1!==G&&{showSizeChanger:!0,showTotal:(e,t)=>`Showing records ${t[0]}-${t[1]} of ${e}`,pageSizeOptions:["10","20","50","100"],defaultPageSize:20,...G},U=e=>{if("function"==typeof z)return`resource-list-item-${z(e)}`;return`resource-list-item-${e[z]??z}`};return e.jsxs(f,{"data-testid":"resource-list-container",children:[_&&e.jsx(u,{children:e.jsxs(w,{children:[e.jsxs(j,{children:[r,c&&e.jsx(S,{placeholder:l,onSearch:c,prefix:e.jsx(i,{}),allowClear:!0,autoComplete:"off","data-testid":"resource-list-search"},l),e.jsx($,{"data-testid":"resource-list-filters",children:d})]}),g&&e.jsx(y,{"data-testid":"resource-list-actions",children:g})]})}),s?e.jsx(b,{"data-testid":"resource-list-loading",children:e.jsx(p,{size:"large"})}):0===n.length?e.jsx(h,{description:e.jsxs(v,{children:[e.jsx(R,{children:A}),e.jsx(T,{children:D?`Get started by creating your first ${q}`:`No ${H} found. Try adjusting your search criteria.`}),(D||L)&&e.jsxs(k,{children:[D&&e.jsx(m,{title:X,children:e.jsx(C,{type:"primary",icon:e.jsx(t,{}),onClick:D,"data-testid":"resource-list-create-new","aria-label":X})}),L&&e.jsx(m,{title:"Refresh",children:e.jsx(E,{icon:e.jsx(a,{}),onClick:L,"data-testid":"resource-list-refresh","aria-label":"Refresh"})})]})]}),image:h.PRESENTED_IMAGE_SIMPLE,"data-testid":"resource-list-empty"}):e.jsx(M,{children:e.jsx(x,{columns:o,dataSource:n,rowKey:z,pagination:K,onRow:(e,t)=>({...I?.(e,t),"data-testid":U(e)}),rowSelection:N,scroll:{x:!0},"data-testid":"resource-list-table"})})]})}export{P as R};
