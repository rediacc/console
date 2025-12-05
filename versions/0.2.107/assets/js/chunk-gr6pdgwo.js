import{j as e}from"./chunk-DUi8bg1D.js";import{d as t,$ as i,L as a,bR as s,bS as r,X as n}from"../index-DldRJJRQ.js";import{S as o}from"./chunk-DEO1aopL.js";import{R as l}from"./chunk-143Yqtwm.js";import{I as c,C as d,S as h,c as p,E as x,s as m,F as u}from"./chunk-CX_EivFx.js";const g=t(d)`
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
`,y=t.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({theme:e})=>e.spacing.SM}px;

  @media (max-width: 768px) {
    width: 100%;
    justify-content: flex-end;
  }
`,$=t(c.Search)`
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
`,S=t(h).attrs({orientation:"vertical",align:"center",size:"middle"})`
  text-align: center;
  padding: ${({theme:e})=>e.spacing.LG}px;
`,R=t(h).attrs({size:"small"})`
  display: flex;
  justify-content: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,v=i`
  min-height: ${({theme:e})=>e.dimensions.INPUT_HEIGHT}px;
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
`,C=t(p)`
  && {
    ${v};
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
`,T=t(p)`
  && {
    ${v};
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

`;function E({title:t,loading:i=!1,data:c=[],columns:d,searchPlaceholder:h="Search...",onSearch:p,filters:v,actions:E,rowKey:M="id",emptyText:G="No data available",pagination:I,onRow:N,rowSelection:P,onCreateNew:z,onRefresh:D,createButtonText:L="Create New",emptyDescription:H,resourceType:_="items"}){const B=Boolean(t||p||v||E),X=H||G,A=_&&_.endsWith("s")?_.slice(0,-1):_,K=!1!==I&&{showSizeChanger:!0,size:"small",showTotal:(e,t)=>`Showing records ${t[0]}-${t[1]} of ${e}`,pageSizeOptions:["10","20","50","100"],defaultPageSize:20,...I},U=e=>{if("function"==typeof M)return`resource-list-item-${M(e)}`;return`resource-list-item-${e[M]??M}`};return e.jsxs(g,{"data-testid":"resource-list-container",children:[B&&e.jsx(f,{children:e.jsxs(w,{children:[e.jsxs(j,{children:[t,p&&e.jsx($,{placeholder:h,onSearch:p,prefix:e.jsx(o,{}),allowClear:!0,autoComplete:"off","data-testid":"resource-list-search"},h),e.jsx(b,{"data-testid":"resource-list-filters",children:v})]}),E&&e.jsx(y,{"data-testid":"resource-list-actions",children:E})]})}),e.jsx(a,{loading:i,centered:!0,minHeight:240,children:0===c.length?e.jsx(x,{description:e.jsxs(S,{children:[e.jsx(s,{children:X}),e.jsx(r,{children:z?`Get started by creating your first ${A}`:`No ${_} found. Try adjusting your search criteria.`}),(z||D)&&e.jsxs(R,{children:[z&&e.jsx(m,{title:L,children:e.jsx(C,{type:"primary",icon:e.jsx(n,{}),onClick:z,"data-testid":"resource-list-create-new","aria-label":L})}),D&&e.jsx(m,{title:"Refresh",children:e.jsx(T,{icon:e.jsx(l,{}),onClick:D,"data-testid":"resource-list-refresh","aria-label":"Refresh"})})]})]}),image:x.PRESENTED_IMAGE_SIMPLE,"data-testid":"resource-list-empty"}):e.jsx(k,{children:e.jsx(u,{columns:d,dataSource:c,rowKey:M,pagination:K,onRow:(e,t)=>({...N?.(e,t),"data-testid":U(e)}),rowSelection:P,scroll:{x:!0},"data-testid":"resource-list-table"})})})]})}export{E as R};
