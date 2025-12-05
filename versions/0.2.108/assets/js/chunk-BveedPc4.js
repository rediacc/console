import{d as e,Z as t}from"../index-DldRJJRQ.js";import{T as i,S as n,F as s,a as o}from"./chunk-CX_EivFx.js";const{Text:a}=i,r=e.div`
  width: 100%;
  text-align: center;
  padding: ${({$padding:e="LG",theme:t})=>t.spacing[e]}px 0;
  ${({$muted:e,theme:t})=>e&&`color: ${t.colors.textSecondary};`}
`;e(r)``;const c=e(a)`
  && {
    font-size: ${({$size:e="SM",theme:t})=>`${{XS:t.fontSize.XS,SM:t.fontSize.CAPTION,BASE:t.fontSize.SM}[e]}px`};
    color: ${({theme:e})=>e.colors.textSecondary};
  }
`,p=e(a)`
  && {
    font-weight: ${({theme:e})=>e.fontWeight.SEMIBOLD};
    font-size: ${({$size:e="LG",theme:t})=>`${{SM:t.fontSize.SM,BASE:t.fontSize.BASE,LG:t.fontSize.LG,XL:t.fontSize.XL}[e]}px`};
    color: ${({$color:e,$variant:t="default",theme:i})=>{if(e)return e;switch(t){case"success":return i.colors.success;case"warning":return i.colors.warning;case"error":return i.colors.error;case"info":return i.colors.info;default:return i.colors.textPrimary}}};
  }
`,d=e.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
`;e.div`
  display: flex;
  align-items: ${({$align:e="center"})=>e};
  justify-content: space-between;
  flex-wrap: wrap;
  gap: ${({$spacing:e="MD",theme:t})=>t.spacing[e]}px;
`;const l=e.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,m=e.div`
  display: flex;
  gap: ${({$spacing:e="SM",theme:t})=>t.spacing[e]}px;
  flex-wrap: wrap;
  justify-content: ${({$justify:e="flex-end"})=>e};
`;e.div`
  display: inline-flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,e.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.MD}px;
  margin-bottom: ${({$margin:e="LG",theme:t})=>t.spacing[e]}px;
`;const $=e(n).attrs({orientation:"vertical",size:"large"})`
  width: 100%;
`,h=e.div`
  display: inline-flex;
  align-items: ${({$align:e="center"})=>e};
  gap: ${({theme:e})=>e.spacing.SM}px;
  flex-wrap: wrap;
`;e(s)`
  .ant-spin-nested-loading {
    opacity: ${({$isLoading:e})=>e?.65:1};
    transition: ${({theme:e})=>e.transitions.DEFAULT};
  }
`;const g=e(t)`
  && {
    ${({$hasLabel:e,theme:t})=>e?`\n      min-width: ${t.dimensions.CONTROL_HEIGHT}px;\n      padding: 0 ${t.spacing.SM}px;\n      gap: ${t.spacing.XS}px;\n    `:`\n      width: ${t.dimensions.CONTROL_HEIGHT}px;\n    `}
    min-height: ${({theme:e})=>e.dimensions.CONTROL_HEIGHT}px;
    border-radius: ${({theme:e})=>e.borderRadius.MD}px;
  }
`;e.hr`
  border: none;
  height: 1px;
  width: 100%;
  background-color: ${({theme:e})=>e.colors.borderSecondary};
  margin: ${({theme:e})=>e.spacing.MD}px 0;
`,e.span`
  width: 8px;
  height: 8px;
  border-radius: ${({theme:e})=>e.borderRadius.FULL}px;
  background-color: ${({theme:e,$variant:t="info"})=>{const i=t in e.colors?t:"info";return e.colors[i]}};
  flex-shrink: 0;
`;const x=e(o)`
  &.ant-select {
    width: 100%;

    .ant-select-selector {
      min-height: ${({$compact:e,theme:t})=>e?t.dimensions.INPUT_HEIGHT_SM:t.dimensions.INPUT_HEIGHT}px;
      border-radius: ${({theme:e})=>e.borderRadius.MD}px;
      background-color: ${({theme:e})=>e.colors.inputBg};
      border-color: ${({theme:e})=>e.colors.inputBorder};
      padding: 0 ${({theme:e})=>e.spacing.SM}px;
      transition: ${({theme:e})=>e.transitions.DEFAULT};
    }

    &.ant-select-focused .ant-select-selector {
      border-color: ${({theme:e})=>e.colors.primary};
      box-shadow: 0 0 0 1px ${({theme:e})=>e.colors.primary};
    }
  }
`;export{m as A,r as C,l as F,h as I,x as M,c as S,g as T,p as a,$ as b,d as c};
