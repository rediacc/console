import{j as e}from"./chunk-BcoMUYMA.js";import{d as t,cm as i,cn as s,a as r,A as a,as as n,l as o,U as c,L as l,c as d,e as h,ad as m}from"../index-BlP7GtlN.js";import"./chunk-Dx23Oqz1.js";import{R as p}from"./chunk-WWAPff2e.js";import{R as x}from"./chunk-BBDGMQYU.js";import{S as u}from"./chunk-DSgwHKDs.js";import{E as f}from"./chunk-3AIKJ4WW.js";const g=t(r)`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.XL}px;
    border-color: ${({theme:e})=>e.colors.borderSecondary};
    box-shadow: ${({theme:e})=>e.shadows.CARD};
    background-color: ${({theme:e})=>e.colors.bgPrimary};
  }
`,j=t.div`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
`,$=t.div`
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.MD}px;

  ${i.tablet`
    flex-direction: column;
    align-items: stretch;
  `}
`,w=t.div`
  display: flex;
  flex: 1 1 auto;
  min-width: 0;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.MD}px;

  ${i.tablet`
    flex-direction: column;
    align-items: stretch;
    width: 100%;
  `}
`,y=t.div`
  display: flex;
  align-items: center;
`,b=t(a)`
  ${i.tablet`
    width: 100%;
    justify-content: flex-end;
  `}
`,R=t(n)`
  && {
    width: ${({theme:e})=>e.dimensions.SEARCH_INPUT_WIDTH}px;
    min-height: ${({theme:e})=>e.dimensions.FORM_CONTROL_HEIGHT}px;
    border-radius: ${({theme:e})=>e.borderRadius.LG}px;
  }

  ${i.tablet`
    && {
      width: 100%;
    }
  `}
`,S=t(o).attrs({direction:"vertical",align:"center",gap:"md"})`
  text-align: center;
  padding: ${({theme:e})=>e.spacing.LG}px;
`,T=t(o).attrs({direction:"horizontal",gap:"sm"})`
  display: flex;
  justify-content: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,C=s`
  min-height: ${({theme:e})=>e.dimensions.FORM_CONTROL_HEIGHT}px;
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
`;t(c)`
  && {
    ${C};
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
`;const k=t(c).attrs({iconOnly:!0})`
  && {
    ${C};
  }
`;function E({title:t,loading:i=!1,data:s=[],columns:r,searchPlaceholder:a="Search...",onSearch:n,filters:o,actions:C,rowKey:E="id",emptyText:v="No data available",pagination:L,onRow:M,rowSelection:N,onCreateNew:O,onRefresh:_,createButtonText:D="Create New",emptyDescription:G,resourceType:H="items"}){const z=Boolean(t||n||o||C),I=G||v,P=H&&H.endsWith("s")?H.slice(0,-1):H,A=!1!==L&&{showSizeChanger:!0,size:"small",showTotal:(e,t)=>`Showing records ${t[0]}-${t[1]} of ${e}`,pageSizeOptions:["10","20","50","100"],defaultPageSize:20,...L},B=e=>{if("function"==typeof E)return`resource-list-item-${E(e)}`;return`resource-list-item-${e[E]??E}`};return e.jsxs(g,{"data-testid":"resource-list-container",children:[z&&e.jsx(j,{children:e.jsxs($,{children:[e.jsxs(w,{children:[t,n&&e.jsx(R,{placeholder:a,onSearch:n,prefix:e.jsx(u,{}),allowClear:!0,autoComplete:"off","data-testid":"resource-list-search"},a),e.jsx(y,{"data-testid":"resource-list-filters",children:o})]}),C&&e.jsx(b,{"data-testid":"resource-list-actions",children:C})]})}),e.jsx(l,{loading:i,centered:!0,minHeight:240,children:0===s.length?e.jsx(f,{description:e.jsxs(S,{children:[e.jsx(d,{variant:"title",children:I}),e.jsx(d,{variant:"description",children:O?`Get started by creating your first ${P}`:`No ${H} found. Try adjusting your search criteria.`}),(O||_)&&e.jsxs(T,{children:[O&&e.jsx(h,{title:D,children:e.jsx(c,{icon:e.jsx(m,{}),onClick:O,"data-testid":"resource-list-create-new","aria-label":D})}),_&&e.jsx(h,{title:"Refresh",children:e.jsx(k,{icon:e.jsx(x,{}),onClick:_,"data-testid":"resource-list-refresh","aria-label":"Refresh"})})]})]}),image:f.PRESENTED_IMAGE_SIMPLE,"data-testid":"resource-list-empty"}):e.jsx(p,{columns:r,dataSource:s,rowKey:E,pagination:A,onRow:(e,t)=>({...M?.(e,t),"data-testid":B(e)}),rowSelection:N,scroll:{x:!0},"data-testid":"resource-list-table"})})]})}export{E as R};
