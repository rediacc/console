import{d as i,P as t,aj as a,ak as e,b as s,a as o}from"../index-CBjoh7UE.js";import"./chunk-DH1Qig9d.js";import{d as n,a0 as m}from"./chunk-BRjXT_03.js";const d=i(t)`
  height: 100%;
`,r=i(m)`
  margin-bottom: ${({theme:i})=>i.spacing.SM}px;
`,h=i(a)`
  margin-bottom: ${({theme:i})=>i.spacing.LG}px;
`,p=i(e)`
  align-items: flex-start;
`,l=i.div`
  flex: 1 1 auto;
  min-width: 0;
`,x=i(s).attrs({$gap:"MD"})`
  margin-bottom: ${({theme:i})=>i.spacing.SM}px;
`,{Title:$}=n,c=i($)`
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
`,v=i.div`
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
`,u=i.div`
  max-width: ${({theme:i})=>i.dimensions.ERROR_WRAPPER_WIDTH}px;
  margin: 0 auto;
`,b=i(o)`
  display: flex;
  flex-direction: column;
`;export{r as B,v as D,u as E,b as F,h as H,f as L,d as P,g as S,l as T,p as a,x as b,c};
