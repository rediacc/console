import{d as i}from"./chunk-BtZST8U3.js";import{P as e}from"../index-CEPyNj08.js";import{T as a,C as t,J as s}from"./chunk-B6OG5Vq-.js";const n=i(e)`
  height: 100%;
`,o=i(t)`
  height: 100%;
  display: flex;
  flex-direction: column;
`,p=i(s)`
  margin-bottom: ${({theme:i})=>i.spacing.SM}px;
`,l=i.div`
  display: flex;
  flex-direction: column;
  gap: ${({theme:i})=>i.spacing.MD}px;
  margin-bottom: ${({theme:i})=>i.spacing.LG}px;
`,d=i.div`
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: ${({theme:i})=>i.spacing.MD}px;
`,r=i.div`
  flex: 1 1 auto;
  min-width: 0;
`,x=i.div`
  display: flex;
  align-items: center;
  gap: ${({theme:i})=>i.spacing.MD}px;
  margin-bottom: ${({theme:i})=>i.spacing.SM}px;
`,{Title:m}=a,c=i(m)`
  && {
    margin: 0;
  }
`,g=i.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${({theme:i})=>i.spacing.SM}px;
`,h=i.div`
  display: flex;
  gap: ${({theme:i})=>i.spacing.SM}px;
  flex-wrap: wrap;
  justify-content: flex-end;
`,f=i.div`
  display: flex;
  flex: 1;
  overflow: hidden;
  position: relative;
`,$=i.div`
  width: ${({$showDetail:i,$detailWidth:e})=>i?`calc(100% - ${e}px)`:"100%"};
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
`,w=i.div`
  text-align: center;
  padding: ${({theme:i})=>i.spacing[6]}px 0;
  color: ${({theme:i})=>i.colors.textSecondary};
`,u=i.div`
  max-width: 480px;
  margin: 0 auto;
`;export{h as A,p as B,w as C,v as D,u as E,o as F,l as H,$ as L,n as P,f as S,r as T,d as a,x as b,c,g as d};
