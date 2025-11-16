import{d as e}from"./chunk-CsUqxJyM.js";import{P as i}from"../index-BuqOOjvw.js";import{T as t,C as a,K as s,B as n}from"./chunk-DcGI-zRP.js";const p=e(i)`
  height: 100%;
`,o=e(a)`
  height: 100%;
  display: flex;
  flex-direction: column;
`,d=e(s)`
  margin-bottom: ${({theme:e})=>e.spacing.SM}px;
`,l=e.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:e})=>e.spacing.MD}px;
  margin-bottom: ${({theme:e})=>e.spacing.LG}px;
`,r=e.div`
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: ${({theme:e})=>e.spacing.MD}px;
`,x=e.div`
  flex: 1 1 auto;
  min-width: 0;
`,m=e.div`
  display: flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.MD}px;
  margin-bottom: ${({theme:e})=>e.spacing.SM}px;
`,{Title:c}=t,h=e(c)`
  && {
    margin: 0;
  }
`,g=e.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({theme:e})=>e.spacing.SM}px;
`,f=e.div`
  display: flex;
  gap: ${({theme:e})=>e.spacing.SM}px;
  flex-wrap: wrap;
  justify-content: flex-end;
`,$=e(n)`
  min-width: ${({theme:e})=>e.spacing[6]}px;
  min-height: ${({theme:e})=>e.spacing[6]}px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: ${({theme:e})=>e.borderRadius.MD}px;
`,u=e.div`
  display: flex;
  flex: 1;
  overflow: hidden;
  position: relative;
`,v=e.div`
  width: ${({$showDetail:e,$detailWidth:i})=>e?`calc(100% - ${i}px)`:"100%"};
  height: 100%;
  overflow: auto;
  min-width: 300px;
  transition: width 0.3s ease-in-out;
`,w=e.div`
  position: fixed;
  top: 0;
  left: 0;
  right: ${({$right:e})=>`${e}px`};
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.4);
  opacity: ${({$visible:e})=>e?1:0};
  transition: opacity 250ms ease-in-out, right 0.3s ease-in-out;
  z-index: ${({theme:e})=>e.zIndex.MODAL};
  pointer-events: ${({$visible:e})=>e?"auto":"none"};
`,y=e.div`
  text-align: center;
  padding: ${({theme:e})=>e.spacing[6]}px 0;
  color: ${({theme:e})=>e.colors.textSecondary};
`,b=e.div`
  max-width: 480px;
  margin: 0 auto;
`;export{f as A,d as B,y as C,w as D,b as E,o as F,l as H,$ as I,v as L,p as P,u as S,x as T,r as a,m as b,h as c,g as d};
