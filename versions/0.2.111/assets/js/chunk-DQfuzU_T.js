import{d as i,P as t,aj as a,ak as s,b as e}from"../index-CytpUOV-.js";import{d as o,Y as n}from"./chunk-CRSiH6gg.js";const r=i(t)`
  height: 100%;
`,d=i(n)`
  margin-bottom: ${({theme:i})=>i.spacing.SM}px;
`,m=i(a)`
  margin-bottom: ${({theme:i})=>i.spacing.LG}px;
`,p=i(s)`
  align-items: flex-start;
`,h=i.div`
  flex: 1 1 auto;
  min-width: 0;
`,g=i(e).attrs({$gap:"MD"})`
  margin-bottom: ${({theme:i})=>i.spacing.SM}px;
`,{Title:l}=o,x=i(l)`
  && {
    margin: 0;
  }
`,$=i.div`
  display: flex;
  flex: 1;
  overflow: hidden;
  position: relative;
`,c=i.div`
  width: ${({$showDetail:i,$detailWidth:t})=>i?`calc(100% - ${t}px)`:"100%"};
  height: 100%;
  overflow: auto;
  min-width: 300px;
  transition: width 0.3s ease-in-out;
`,v=i.div`
  position: fixed;
  top: 0;
  left: 0;
  right: ${({$right:i})=>`${i}px`};
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.4);
  opacity: ${({$visible:i})=>i?1:0};
  transition: opacity 250ms ease-in-out, right 0.3s ease-in-out;
  z-index: ${({theme:i})=>i.zIndex.MODAL};
  pointer-events: ${({$visible:i})=>i?"auto":"none"};
`,b=i.div`
  max-width: 480px;
  margin: 0 auto;
`;export{d as B,v as D,b as E,m as H,c as L,r as P,$ as S,h as T,p as a,g as b,x as c};
