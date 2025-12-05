import{j as e}from"./chunk-DUi8bg1D.js";import{b as t}from"./chunk-DDwtzQW6.js";import{d as o}from"../index-DldRJJRQ.js";const r=o.div`
  position: relative;
  height: ${({$height:e})=>"number"==typeof e?`${e}px`:e};
  border: 1px solid ${({theme:e})=>e.colors.borderPrimary};
  border-radius: ${({theme:e})=>e.borderRadius.LG}px;
  overflow: hidden;
  background-color: ${({theme:e})=>e.colors.bgPrimary};
  box-shadow: ${({theme:e})=>e.shadows.SM};
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: ${({theme:e})=>e.fontSize.SM}px;
  line-height: ${({theme:e})=>e.lineHeight.RELAXED};
`,i=o.textarea`
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
`,n=o.div`
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
`,s=({value:o,onChange:s,readOnly:a=!1,height:l="400px",className:h="","data-testid":c,onFormatReady:m})=>{const[d,u]=t.useState(o),[f,p]=t.useState(null),[g,b]=t.useState(o);if(o!==g)if(b(o),u(o),o.trim())try{JSON.parse(o),p(null)}catch(x){p(x.message)}else p(null);const $=t.useCallback(()=>{if(d.trim())try{const e=JSON.parse(d),t=JSON.stringify(e,null,2);u(t),s?.(t),p(null)}catch(x){p(x.message)}},[d,s]);t.useEffect(()=>{m&&m($)},[m,$]);return e.jsxs(r,{className:h,$height:l,children:[e.jsx(i,{value:d,onChange:e=>{const t=e.target.value;u(t),(t=>{if(t.trim())try{JSON.parse(t),p(null)}catch(e){p(e.message)}else p(null)})(t),s?.(t)},onKeyDown:e=>{if("Tab"===e.key){e.preventDefault();const t=e.currentTarget,o=t.selectionStart,r=t.selectionEnd,i=d.substring(0,o)+"  "+d.substring(r);u(i),s?.(i),t.selectionStart=t.selectionEnd=o+2}},readOnly:a,spellCheck:!1,autoComplete:"off",autoCorrect:"off",autoCapitalize:"off","data-testid":c}),f&&e.jsxs(n,{children:["JSON Error: ",f]})]})};export{s as S};
