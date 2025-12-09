import{j as e}from"./chunk-BVJi4K5d.js";import{b as t}from"./chunk-RZFQ-vRJ.js";import{h as o,d as r}from"../index-CytpUOV-.js";const n=r.div`
  position: relative;
  height: ${({$height:e})=>"number"==typeof e?`${e}px`:e};
  ${o("borderPrimary")}
  overflow: hidden;
  background-color: ${({theme:e})=>e.colors.bgPrimary};
  box-shadow: ${({theme:e})=>e.shadows.SM};
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: ${({theme:e})=>e.fontSize.SM}px;
  line-height: ${({theme:e})=>e.lineHeight.RELAXED};
`,i=r.textarea`
  width: 100%;
  height: 100%;
  padding: ${({theme:e})=>e.spacing.MD}px;
  border: none;
  outline: none;
  resize: none;
  background-color: transparent;
  color: ${({theme:e})=>e.colors.textPrimary};
  font-family: inherit;
  font-size: inherit;
  line-height: inherit;
  tab-size: 2;
`,s=r.div`
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: ${({theme:e})=>`${e.spacing.XS}px ${e.spacing.SM}px`};
  background-color: ${({theme:e})=>e.colors.bgError};
  color: ${({theme:e})=>e.colors.error};
  font-size: ${({theme:e})=>e.fontSize.CAPTION}px;
  font-weight: ${({theme:e})=>e.fontWeight.MEDIUM};
  border-top: 1px solid ${({theme:e})=>e.colors.error};
`,a=({value:o,onChange:r,readOnly:a=!1,height:l="400px",className:h="","data-testid":c,onFormatReady:m})=>{const[f,u]=t.useState(o),[d,g]=t.useState(null),[p,$]=t.useState(o);if(o!==p)if($(o),u(o),o.trim())try{JSON.parse(o),g(null)}catch(S){g(S.message)}else g(null);const b=t.useCallback(()=>{if(f.trim())try{const e=JSON.parse(f),t=JSON.stringify(e,null,2);u(t),r?.(t),g(null)}catch(S){g(S.message)}},[f,r]);t.useEffect(()=>{m&&m(b)},[m,b]);return e.jsxs(n,{className:h,$height:l,children:[e.jsx(i,{value:f,onChange:e=>{const t=e.target.value;u(t),(t=>{if(t.trim())try{JSON.parse(t),g(null)}catch(e){g(e.message)}else g(null)})(t),r?.(t)},onKeyDown:e=>{if("Tab"===e.key){e.preventDefault();const t=e.currentTarget,o=t.selectionStart,n=t.selectionEnd,i=f.substring(0,o)+"  "+f.substring(n);u(i),r?.(i),t.selectionStart=t.selectionEnd=o+2}},readOnly:a,spellCheck:!1,autoComplete:"off",autoCorrect:"off",autoCapitalize:"off","data-testid":c}),d&&e.jsxs(s,{children:["JSON Error: ",d]})]})};export{a as S};
