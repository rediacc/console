import{j as e}from"./chunk-DXoLy3RZ.js";import{L as t,v as i}from"../index-CEPyNj08.js";import{S as a}from"./chunk-D83A5xz1.js";import{R as r}from"./chunk-CuBbjl3l.js";import{d as s,a as n}from"./chunk-BtZST8U3.js";import{I as o,T as c,C as l,c as d,B as p,E as h,l as m,F as x}from"./chunk-B6OG5Vq-.js";const{Text:g}=c,f=s(l)`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.XL}px;
    border-color: ${({theme:e})=>e.colors.borderSecondary};
    box-shadow: ${({theme:e})=>e.shadows.CARD};
    background-color: ${({theme:e})=>e.colors.bgPrimary};
  }
`,u=s.div`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
`,w=s.div`
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.MD}px;

  @media (max-width: 768px) {
    flex-direction: column;
    align-items: stretch;
  }
`,j=s.div`
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
`,$=s.div`
  display: flex;
  align-items: center;
`,y=s.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({theme:e})=>e.spacing.SM}px;

  @media (max-width: 768px) {
    width: 100%;
    justify-content: flex-end;
  }
`,S=s(o.Search)`
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
`;s.div`
  text-align: center;
  padding: ${({theme:e})=>e.spacing.XXXXL}px 0;
`;const b=s(d).attrs({direction:"vertical",align:"center",size:"middle"})`
  text-align: center;
  padding: ${({theme:e})=>e.spacing.LG}px;
`,v=s(g)`
  && {
    color: ${({theme:e})=>e.colors.textPrimary};
    font-size: ${({theme:e})=>e.fontSize.BASE}px;
  }
`,R=s(g)`
  && {
    font-size: ${({theme:e})=>e.fontSize.SM}px;
    color: ${({theme:e})=>e.colors.textSecondary};
  }
`,T=s(d).attrs({size:"small"})`
  display: flex;
  justify-content: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,k=n`
  min-height: ${({theme:e})=>e.dimensions.INPUT_HEIGHT}px;
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
`,z=s(p)`
  && {
    ${k};
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
`,C=s(p)`
  && {
    ${k};
  }
`,E=s.div`
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
`;function M({title:s,loading:n=!1,data:o=[],columns:c,searchPlaceholder:l="Search...",onSearch:d,filters:p,actions:g,rowKey:k="id",emptyText:M="No data available",pagination:P,onRow:G,rowSelection:I,onCreateNew:L,onRefresh:N,createButtonText:D="Create New",emptyDescription:X,resourceType:B="items"}){const H=Boolean(s||d||p||g),_=X||M,A=B&&B.endsWith("s")?B.slice(0,-1):B,K=!1!==P&&{showSizeChanger:!0,showTotal:(e,t)=>`Showing records ${t[0]}-${t[1]} of ${e}`,pageSizeOptions:["10","20","50","100"],defaultPageSize:20,...P},U=e=>{if("function"==typeof k)return`resource-list-item-${k(e)}`;return`resource-list-item-${e[k]??k}`};return e.jsxs(f,{"data-testid":"resource-list-container",children:[H&&e.jsx(u,{children:e.jsxs(w,{children:[e.jsxs(j,{children:[s,d&&e.jsx(S,{placeholder:l,onSearch:d,prefix:e.jsx(a,{}),allowClear:!0,autoComplete:"off","data-testid":"resource-list-search"},l),e.jsx($,{"data-testid":"resource-list-filters",children:p})]}),g&&e.jsx(y,{"data-testid":"resource-list-actions",children:g})]})}),e.jsx(t,{loading:n,centered:!0,minHeight:240,children:0===o.length?e.jsx(h,{description:e.jsxs(b,{children:[e.jsx(v,{children:_}),e.jsx(R,{children:L?`Get started by creating your first ${A}`:`No ${B} found. Try adjusting your search criteria.`}),(L||N)&&e.jsxs(T,{children:[L&&e.jsx(m,{title:D,children:e.jsx(z,{type:"primary",icon:e.jsx(i,{}),onClick:L,"data-testid":"resource-list-create-new","aria-label":D})}),N&&e.jsx(m,{title:"Refresh",children:e.jsx(C,{icon:e.jsx(r,{}),onClick:N,"data-testid":"resource-list-refresh","aria-label":"Refresh"})})]})]}),image:h.PRESENTED_IMAGE_SIMPLE,"data-testid":"resource-list-empty"}):e.jsx(E,{children:e.jsx(x,{columns:c,dataSource:o,rowKey:k,pagination:K,onRow:(e,t)=>({...G?.(e,t),"data-testid":U(e)}),rowSelection:I,scroll:{x:!0},"data-testid":"resource-list-table"})})})]})}export{M as R};
