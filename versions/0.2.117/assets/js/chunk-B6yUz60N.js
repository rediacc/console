import{j as e}from"./chunk-DH1Qig9d.js";import{d as t,co as i,ah as a,a as s,A as r,cm as n,k as o,U as c,L as l,c as d,ad as h}from"../index-CBjoh7UE.js";import{R as p}from"./chunk-CoAlwRfP.js";import{S as m}from"./chunk-Bmf4gvFr.js";import{E as x,y as u,F as g}from"./chunk-BRjXT_03.js";const f=t(s)`
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
    min-height: ${({theme:e})=>e.dimensions.INPUT_HEIGHT}px;
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
  min-height: ${({theme:e})=>e.dimensions.INPUT_HEIGHT}px;
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
`;t(c)`
  && {
    ${T};
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
`;const k=t(c).attrs({iconOnly:!0})`
  && {
    ${T};
  }
`,E=t.div`
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
`;function C({title:t,loading:i=!1,data:a=[],columns:s,searchPlaceholder:r="Search...",onSearch:n,filters:o,actions:T,rowKey:C="id",emptyText:I="No data available",pagination:M,onRow:N,rowSelection:P,onCreateNew:D,onRefresh:G,createButtonText:H="Create New",emptyDescription:L,resourceType:_="items"}){const z=Boolean(t||n||o||T),A=L||I,B=_&&_.endsWith("s")?_.slice(0,-1):_,U=!1!==M&&{showSizeChanger:!0,size:"small",showTotal:(e,t)=>`Showing records ${t[0]}-${t[1]} of ${e}`,pageSizeOptions:["10","20","50","100"],defaultPageSize:20,...M},O=e=>{if("function"==typeof C)return`resource-list-item-${C(e)}`;return`resource-list-item-${e[C]??C}`};return e.jsxs(f,{"data-testid":"resource-list-container",children:[z&&e.jsx(j,{children:e.jsxs(w,{children:[e.jsxs($,{children:[t,n&&e.jsx(S,{placeholder:r,onSearch:n,prefix:e.jsx(m,{}),allowClear:!0,autoComplete:"off","data-testid":"resource-list-search"},r),e.jsx(b,{"data-testid":"resource-list-filters",children:o})]}),T&&e.jsx(y,{"data-testid":"resource-list-actions",children:T})]})}),e.jsx(l,{loading:i,centered:!0,minHeight:240,children:0===a.length?e.jsx(x,{description:e.jsxs(R,{children:[e.jsx(d,{variant:"title",children:A}),e.jsx(d,{variant:"description",children:D?`Get started by creating your first ${B}`:`No ${_} found. Try adjusting your search criteria.`}),(D||G)&&e.jsxs(v,{children:[D&&e.jsx(u,{title:H,children:e.jsx(c,{icon:e.jsx(h,{}),onClick:D,"data-testid":"resource-list-create-new","aria-label":H})}),G&&e.jsx(u,{title:"Refresh",children:e.jsx(k,{icon:e.jsx(p,{}),onClick:G,"data-testid":"resource-list-refresh","aria-label":"Refresh"})})]})]}),image:x.PRESENTED_IMAGE_SIMPLE,"data-testid":"resource-list-empty"}):e.jsx(E,{children:e.jsx(g,{columns:s,dataSource:a,rowKey:C,pagination:U,onRow:(e,t)=>({...N?.(e,t),"data-testid":O(e)}),rowSelection:P,scroll:{x:!0},"data-testid":"resource-list-table"})})})]})}export{C as R};
