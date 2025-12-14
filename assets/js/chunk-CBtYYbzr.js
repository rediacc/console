import{j as e}from"./chunk-DH1Qig9d.js";import{d as t,cp as i,aj as a,a as s,A as r,at as n,k as o,U as l,L as c,c as d,ad as h}from"../index-BEvUMz1n.js";import{R as p}from"./chunk-B7O9DEY3.js";import{S as m}from"./chunk-DbLIQOJX.js";import{E as x,y as u,F as g}from"./chunk-BRjXT_03.js";const f=t(s)`
  && {
    border-radius: ${({theme:e})=>e.borderRadius.XL}px;
    border-color: ${({theme:e})=>e.colors.borderSecondary};
    box-shadow: ${({theme:e})=>e.shadows.CARD};
    background-color: ${({theme:e})=>e.colors.bgPrimary};
  }
`,j=t.div`
  margin-bottom: ${({theme:e})=>e.spacing.MD}px;
`,w=t.div`
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.MD}px;

  ${i.tablet`
    flex-direction: column;
    align-items: stretch;
  `}
`,$=t.div`
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
`,b=t.div`
  display: flex;
  align-items: center;
`,y=t(r)`
  ${i.tablet`
    width: 100%;
    justify-content: flex-end;
  `}
`,S=t(n)`
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
`,R=t(o).attrs({direction:"vertical",align:"center",gap:"md"})`
  text-align: center;
  padding: ${({theme:e})=>e.spacing.LG}px;
`,v=t(o).attrs({direction:"horizontal",gap:"sm"})`
  display: flex;
  justify-content: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,T=a`
  min-height: ${({theme:e})=>e.dimensions.FORM_CONTROL_HEIGHT}px;
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
`;t(l)`
  && {
    ${T};
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
`;const C=t(l).attrs({iconOnly:!0})`
  && {
    ${T};
  }
`,k=t.div`
  /* Better scroll experience on mobile devices */
  @media (max-width: ${({theme:e})=>e.breakpoints.MOBILE}px) {
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
`;function E({title:t,loading:i=!1,data:a=[],columns:s,searchPlaceholder:r="Search...",onSearch:n,filters:o,actions:T,rowKey:E="id",emptyText:M="No data available",pagination:L,onRow:O,rowSelection:N,onCreateNew:_,onRefresh:D,createButtonText:G="Create New",emptyDescription:H,resourceType:I="items"}){const P=Boolean(t||n||o||T),z=H||M,A=I&&I.endsWith("s")?I.slice(0,-1):I,B=!1!==L&&{showSizeChanger:!0,size:"small",showTotal:(e,t)=>`Showing records ${t[0]}-${t[1]} of ${e}`,pageSizeOptions:["10","20","50","100"],defaultPageSize:20,...L},F=e=>{if("function"==typeof E)return`resource-list-item-${E(e)}`;return`resource-list-item-${e[E]??E}`};return e.jsxs(f,{"data-testid":"resource-list-container",children:[P&&e.jsx(j,{children:e.jsxs(w,{children:[e.jsxs($,{children:[t,n&&e.jsx(S,{placeholder:r,onSearch:n,prefix:e.jsx(m,{}),allowClear:!0,autoComplete:"off","data-testid":"resource-list-search"},r),e.jsx(b,{"data-testid":"resource-list-filters",children:o})]}),T&&e.jsx(y,{"data-testid":"resource-list-actions",children:T})]})}),e.jsx(c,{loading:i,centered:!0,minHeight:240,children:0===a.length?e.jsx(x,{description:e.jsxs(R,{children:[e.jsx(d,{variant:"title",children:z}),e.jsx(d,{variant:"description",children:_?`Get started by creating your first ${A}`:`No ${I} found. Try adjusting your search criteria.`}),(_||D)&&e.jsxs(v,{children:[_&&e.jsx(u,{title:G,children:e.jsx(l,{icon:e.jsx(h,{}),onClick:_,"data-testid":"resource-list-create-new","aria-label":G})}),D&&e.jsx(u,{title:"Refresh",children:e.jsx(C,{icon:e.jsx(p,{}),onClick:D,"data-testid":"resource-list-refresh","aria-label":"Refresh"})})]})]}),image:x.PRESENTED_IMAGE_SIMPLE,"data-testid":"resource-list-empty"}):e.jsx(k,{children:e.jsx(g,{columns:s,dataSource:a,rowKey:E,pagination:B,onRow:(e,t)=>({...O?.(e,t),"data-testid":F(e)}),rowSelection:N,scroll:{x:!0},"data-testid":"resource-list-table"})})})]})}export{E as R};
