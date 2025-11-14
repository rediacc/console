import{d as e}from"./chunk-VAXc7D1f.js";import{h as t}from"../index-BVkh4HIo.js";import{T as a,o as i,B as n,w as s}from"./chunk-BHacwfgw.js";const{Title:r}=a,o=e.div.attrs({className:"page-container"})`
  width: 100%;
`,p=e(i).attrs({className:"page-card"})``,d=e.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.MD}px;
  margin-bottom: ${({theme:e})=>e.spacing.PAGE_SECTION_GAP}px;
`,m=e.div`
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: ${({theme:e})=>e.spacing.MD}px;
`,c=e.div`
  display: flex;
  flex: 1 1 auto;
  min-width: 0;
  gap: ${({theme:e})=>e.spacing.MD}px;
  align-items: center;
`,l=e.div`
  flex: 1 1 280px;
  min-width: 240px;
`,g=e.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({theme:e})=>e.spacing.SM}px;
  justify-content: flex-end;
`,x=e(n)`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: ${t.DIMENSIONS.CONTROL_HEIGHT}px;
  min-height: ${t.DIMENSIONS.CONTROL_HEIGHT}px;
  border-radius: ${({theme:e})=>e.borderRadius.MD}px;
  transition: ${({theme:e})=>e.transitions.DEFAULT};

  &:not(:disabled):hover {
    transform: translateY(-1px);
    box-shadow: ${({theme:e})=>e.shadows.BUTTON_HOVER};
  }
`;e(r)`
  && {
    margin: 0;
    color: ${({theme:e})=>e.colors.textPrimary};
    font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
  }
`,e.div`
  margin-bottom: ${({theme:e})=>e.spacing.SM}px;
`;const h=e.div`
  min-height: 400px;
`,$=e(s)`
  .ant-spin-nested-loading {
    opacity: ${e=>e.$isLoading?.65:1};
    transition: ${({theme:e})=>e.transitions.DEFAULT};
  }
`;e(a.Paragraph)`
  && {
    margin: 0;
    color: ${({theme:e})=>e.colors.textSecondary};
  }
`,e.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: ${({theme:e})=>e.spacing.MD}px;
`,e.div`
  display: inline-flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.XS}px;
  padding: ${({theme:e})=>e.spacing.XS}px ${({theme:e})=>e.spacing.SM}px;
  border-radius: ${({theme:e})=>e.borderRadius.FULL}px;
  background-color: ${({theme:e})=>e.colors.bgSecondary};
  color: ${({theme:e})=>e.colors.textSecondary};
  font-size: ${({theme:e})=>e.fontSize.CAPTION}px;
`,e.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: ${({theme:e})=>e.spacing.MD}px;
`,e.hr`
  border: none;
  height: 1px;
  width: 100%;
  background-color: ${({theme:e})=>e.colors.borderSecondary};
  margin: ${({theme:e})=>e.spacing.LG}px 0;
`,e.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: ${({theme:e})=>e.spacing.MD}px;
`,e.span`
  display: inline-flex;
  align-items: center;
  padding: ${({theme:e})=>e.spacing.XS}px ${({theme:e})=>e.spacing.SM}px;
  border-radius: ${({theme:e})=>e.borderRadius.FULL}px;
  background-color: ${({theme:e})=>e.colors.bgSecondary};
  color: ${({theme:e})=>e.colors.textSecondary};
  font-size: ${({theme:e})=>e.fontSize.CAPTION}px;
`;export{g as A,c as C,$ as D,l as I,o as P,d as S,p as a,m as b,x as c,h as d};
