import{j as e}from"./chunk-DXoLy3RZ.js";import{L as t,bW as i,bX as a,K as r}from"../index-7i0bsO_E.js";import{S as s}from"./chunk-X-ex5_IH.js";import{R as n}from"./chunk-Bw-nq2BR.js";import{d as o,l}from"./chunk-m5fYU7UF.js";import{I as c,C as d,S as p,c as h,E as m,o as x,F as g}from"./chunk-2wWKRBEk.js";const u=o(d)`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.XL}px;
    border-color: ${({theme:e})=>e.colors.borderSecondary};
    box-shadow: ${({theme:e})=>e.shadows.CARD};
    background-color: ${({theme:e})=>e.colors.bgPrimary};
  }
`,f=o.div`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
`,w=o.div`
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.MD}px;

  @media (max-width: 768px) {
    flex-direction: column;
    align-items: stretch;
  }
`,j=o.div`
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
`,y=o.div`
  display: flex;
  align-items: center;
`,b=o.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({theme:e})=>e.spacing.SM}px;

  @media (max-width: 768px) {
    width: 100%;
    justify-content: flex-end;
  }
`,$=o(c.Search)`
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
`,S=o(p).attrs({direction:"vertical",align:"center",size:"middle"})`
  text-align: center;
  padding: ${({theme:e})=>e.spacing.LG}px;
`,R=o(p).attrs({size:"small"})`
  display: flex;
  justify-content: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,v=l`
  min-height: ${({theme:e})=>e.dimensions.INPUT_HEIGHT}px;
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
`,k=o(h)`
  && {
    ${v};
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
`,T=o(h)`
  && {
    ${v};
  }
`,C=o.div`
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
`;function E({title:o,loading:l=!1,data:c=[],columns:d,searchPlaceholder:p="Search...",onSearch:h,filters:v,actions:E,rowKey:M="id",emptyText:G="No data available",pagination:I,onRow:N,rowSelection:P,onCreateNew:D,onRefresh:L,createButtonText:z="Create New",emptyDescription:H,resourceType:_="items"}){const B=Boolean(o||h||v||E),K=H||G,X=_&&_.endsWith("s")?_.slice(0,-1):_,A=!1!==I&&{showSizeChanger:!0,showTotal:(e,t)=>`Showing records ${t[0]}-${t[1]} of ${e}`,pageSizeOptions:["10","20","50","100"],defaultPageSize:20,...I},U=e=>{if("function"==typeof M)return`resource-list-item-${M(e)}`;return`resource-list-item-${e[M]??M}`};return e.jsxs(u,{"data-testid":"resource-list-container",children:[B&&e.jsx(f,{children:e.jsxs(w,{children:[e.jsxs(j,{children:[o,h&&e.jsx($,{placeholder:p,onSearch:h,prefix:e.jsx(s,{}),allowClear:!0,autoComplete:"off","data-testid":"resource-list-search"},p),e.jsx(y,{"data-testid":"resource-list-filters",children:v})]}),E&&e.jsx(b,{"data-testid":"resource-list-actions",children:E})]})}),e.jsx(t,{loading:l,centered:!0,minHeight:240,children:0===c.length?e.jsx(m,{description:e.jsxs(S,{children:[e.jsx(i,{children:K}),e.jsx(a,{children:D?`Get started by creating your first ${X}`:`No ${_} found. Try adjusting your search criteria.`}),(D||L)&&e.jsxs(R,{children:[D&&e.jsx(x,{title:z,children:e.jsx(k,{type:"primary",icon:e.jsx(r,{}),onClick:D,"data-testid":"resource-list-create-new","aria-label":z})}),L&&e.jsx(x,{title:"Refresh",children:e.jsx(T,{icon:e.jsx(n,{}),onClick:L,"data-testid":"resource-list-refresh","aria-label":"Refresh"})})]})]}),image:m.PRESENTED_IMAGE_SIMPLE,"data-testid":"resource-list-empty"}):e.jsx(C,{children:e.jsx(g,{columns:d,dataSource:c,rowKey:M,pagination:A,onRow:(e,t)=>({...N?.(e,t),"data-testid":U(e)}),rowSelection:P,scroll:{x:!0},"data-testid":"resource-list-table"})})})]})}export{E as R};
