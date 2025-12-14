import{d as i,P as t,al as a,am as e,b as s,a as o}from"../index-ClLYmVcU.js";import"./chunk-BcoMUYMA.js";import"./chunk-Dx23Oqz1.js";import{d as n,$ as m}from"./chunk-3AIKJ4WW.js";const r=i(t)`
  height: 100%;
`,d=i(m)`
  margin-bottom: ${({theme:i})=>i.spacing.SM}px;
`,h=i(a)`
  margin-bottom: ${({theme:i})=>i.spacing.LG}px;
`,p=i(e)`
  align-items: flex-start;
`,l=i.div`
  flex: 1 1 auto;
  min-width: 0;
`,$=i(s).attrs({$gap:"MD"})`
  margin-bottom: ${({theme:i})=>i.spacing.SM}px;
`,{Title:x}=n,c=i(x)`
  && {
    margin: 0;
  }
`,g=i.div`
  display: flex;
  flex: 1;
  overflow: hidden;
  position: relative;
`,f=i.div`
  width: ${({$showDetail:i,$detailWidth:t})=>i?`calc(100% - ${t}px)`:"100%"};
  height: 100%;
  overflow: auto;
  min-width: ${({theme:i})=>i.dimensions.SPLIT_PANEL_MIN_WIDTH}px;
  transition: width 0.3s ease-in-out;
`,u=i.div`
  position: fixed;
  top: 0;
  left: 0;
  right: ${({$right:i})=>`${i}px`};
  bottom: 0;
  background-color: ${({theme:i})=>i.overlays.backdrop};
  opacity: ${({$visible:i})=>i?1:0};
  transition: opacity 250ms ease-in-out, right 0.3s ease-in-out;
  z-index: ${({theme:i})=>i.zIndex.MODAL};
  pointer-events: ${({$visible:i})=>i?"auto":"none"};
`,v=i.div`
  max-width: ${({theme:i})=>i.dimensions.ERROR_WRAPPER_WIDTH}px;
  margin: 0 auto;
`,b=i(o)`
  display: flex;
  flex-direction: column;
`;export{d as B,u as D,v as E,b as F,h as H,f as L,r as P,g as S,l as T,p as a,$ as b,c};
