import{d as i}from"./chunk-m5fYU7UF.js";import{P as a,A as e,F as t}from"../index-BR9NOAob.js";import{T as s,C as o,N as n}from"./chunk-2wWKRBEk.js";const p=i(a)`
  height: 100%;
`,d=i(o)`
  height: 100%;
  display: flex;
  flex-direction: column;
`,r=i(n)`
  margin-bottom: ${({theme:i})=>i.spacing.SM}px;
`,l=i(e)`
  margin-bottom: ${({theme:i})=>i.spacing.LG}px;
`,m=i(t)`
  align-items: flex-start;
`,x=i.div`
  flex: 1 1 auto;
  min-width: 0;
`,h=i.div`
  display: flex;
  align-items: center;
  gap: ${({theme:i})=>i.spacing.MD}px;
  margin-bottom: ${({theme:i})=>i.spacing.SM}px;
`,{Title:g}=s,c=i(g)`
  && {
    margin: 0;
  }
`,f=i.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({theme:i})=>i.spacing.SM}px;
`,$=i.div`
  display: flex;
  gap: ${({theme:i})=>i.spacing.SM}px;
  flex-wrap: wrap;
  justify-content: flex-end;
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
`,b=i.div`
  text-align: center;
  padding: ${({theme:i})=>i.spacing[6]}px 0;
  color: ${({theme:i})=>i.colors.textSecondary};
`,y=i.div`
  max-width: 480px;
  margin: 0 auto;
`;export{$ as A,r as B,b as C,w as D,y as E,d as F,l as H,u as L,p as P,v as S,x as T,m as a,h as b,c,f as d};
