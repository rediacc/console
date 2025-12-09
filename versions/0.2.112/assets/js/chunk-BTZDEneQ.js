import{j as e}from"./chunk-DafPgHWS.js";import{d as t,ah as i,a,A as r,cl as s,l as n,U as o,L as c,c as l,ad as d}from"../index-VtVQDmDS.js";import{R as h}from"./chunk-DQf_Ugvv.js";import{S as x}from"./chunk-OuU-RzcS.js";import{E as m,w as p,F as u}from"./chunk-DsAsudOV.js";const g=t(a)`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.XL}px;
    border-color: ${({theme:e})=>e.colors.borderSecondary};
    box-shadow: ${({theme:e})=>e.shadows.CARD};
    background-color: ${({theme:e})=>e.colors.bgPrimary};
  }
`,f=t.div`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
`,w=t.div`
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.MD}px;

  @media (max-width: 768px) {
    flex-direction: column;
    align-items: stretch;
  }
`,j=t.div`
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
`,b=t.div`
  display: flex;
  align-items: center;
`,y=t(r)`
  @media (max-width: 768px) {
    width: 100%;
    justify-content: flex-end;
  }
`,$=t(s)`
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
`,S=t(n).attrs({direction:"vertical",align:"center",gap:"md"})`
  text-align: center;
  padding: ${({theme:e})=>e.spacing.LG}px;
`,v=t(n).attrs({direction:"horizontal",gap:"sm"})`
  display: flex;
  justify-content: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,R=i`
  min-height: ${({theme:e})=>e.dimensions.INPUT_HEIGHT}px;
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
`;t(o)`
  && {
    ${R};
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
`;const T=t(o).attrs({iconOnly:!0})`
  && {
    ${R};
  }
`,k=t.div`
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

`;function C({title:t,loading:i=!1,data:a=[],columns:r,searchPlaceholder:s="Search...",onSearch:n,filters:R,actions:C,rowKey:E="id",emptyText:G="No data available",pagination:M,onRow:N,rowSelection:P,onCreateNew:z,onRefresh:D,createButtonText:I="Create New",emptyDescription:L,resourceType:H="items"}){const _=Boolean(t||n||R||C),A=L||G,B=H&&H.endsWith("s")?H.slice(0,-1):H,U=!1!==M&&{showSizeChanger:!0,size:"small",showTotal:(e,t)=>`Showing records ${t[0]}-${t[1]} of ${e}`,pageSizeOptions:["10","20","50","100"],defaultPageSize:20,...M},K=e=>{if("function"==typeof E)return`resource-list-item-${E(e)}`;return`resource-list-item-${e[E]??E}`};return e.jsxs(g,{"data-testid":"resource-list-container",children:[_&&e.jsx(f,{children:e.jsxs(w,{children:[e.jsxs(j,{children:[t,n&&e.jsx($,{placeholder:s,onSearch:n,prefix:e.jsx(x,{}),allowClear:!0,autoComplete:"off","data-testid":"resource-list-search"},s),e.jsx(b,{"data-testid":"resource-list-filters",children:R})]}),C&&e.jsx(y,{"data-testid":"resource-list-actions",children:C})]})}),e.jsx(c,{loading:i,centered:!0,minHeight:240,children:0===a.length?e.jsx(m,{description:e.jsxs(S,{children:[e.jsx(l,{variant:"title",children:A}),e.jsx(l,{variant:"description",children:z?`Get started by creating your first ${B}`:`No ${H} found. Try adjusting your search criteria.`}),(z||D)&&e.jsxs(v,{children:[z&&e.jsx(p,{title:I,children:e.jsx(o,{icon:e.jsx(d,{}),onClick:z,"data-testid":"resource-list-create-new","aria-label":I})}),D&&e.jsx(p,{title:"Refresh",children:e.jsx(T,{icon:e.jsx(h,{}),onClick:D,"data-testid":"resource-list-refresh","aria-label":"Refresh"})})]})]}),image:m.PRESENTED_IMAGE_SIMPLE,"data-testid":"resource-list-empty"}):e.jsx(k,{children:e.jsx(u,{columns:r,dataSource:a,rowKey:E,pagination:U,onRow:(e,t)=>({...N?.(e,t),"data-testid":K(e)}),rowSelection:P,scroll:{x:!0},"data-testid":"resource-list-table"})})})]})}export{C as R};
