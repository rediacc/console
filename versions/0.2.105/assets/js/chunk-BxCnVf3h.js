import{d as i,P as a,K as t,N as e}from"../index-DldRJJRQ.js";import{C as s}from"./chunk-BveedPc4.js";import{T as o,C as n,U as p}from"./chunk-CX_EivFx.js";const r=i(a)`
  height: 100%;
`,d=i(n)`
  height: 100%;
  display: flex;
  flex-direction: column;
`,m=i(p)`
  margin-bottom: ${({theme:i})=>i.spacing.SM}px;
`,l=i(t)`
  margin-bottom: ${({theme:i})=>i.spacing.LG}px;
`,h=i(e)`
  align-items: flex-start;
`,x=i.div`
  flex: 1 1 auto;
  min-width: 0;
`,g=i.div`
  display: flex;
  align-items: center;
  gap: ${({theme:i})=>i.spacing.MD}px;
  margin-bottom: ${({theme:i})=>i.spacing.SM}px;
`,{Title:c}=o,$=i(c)`
  && {
    margin: 0;
  }
`,f=i.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({theme:i})=>i.spacing.SM}px;
`,v=i.div`
  display: flex;
  flex: 1;
  overflow: hidden;
  position: relative;
`,u=i.div`
  width: ${({$showDetail:i,$detailWidth:a})=>i?`calc(100% - ${a}px)`:"100%"};
  height: 100%;
  overflow: auto;
  min-width: 300px;
  transition: width 0.3s ease-in-out;
`,w=i.div`
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
`,b=s,y=i.div`
  max-width: 480px;
  margin: 0 auto;
`;export{m as B,b as C,w as D,y as E,d as F,l as H,u as L,r as P,v as S,x as T,h as a,g as b,$ as c,f as d};
