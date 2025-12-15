import{j as e}from"./chunk-BcoMUYMA.js";import{b as t}from"./chunk-Dx23Oqz1.js";import{h as o,d as r}from"../index-BH3CdaUu.js";const n=r.div`
  position: relative;
  height: ${({$height:e})=>"number"==typeof e?`${e}px`:e};
  ${o("borderPrimary")}
  overflow: hidden;
  background-color: ${({theme:e})=>e.colors.bgPrimary};
  box-shadow: ${({theme:e})=>e.shadows.SM};
  font-family: ${({theme:e})=>e.fontFamily.MONO};
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
  font-size: ${({theme:e})=>e.fontSize.XS}px;
  font-weight: ${({theme:e})=>e.fontWeight.MEDIUM};
  border-top: 1px solid ${({theme:e})=>e.colors.error};
`,a=({value:o,onChange:r,readOnly:a=!1,height:l="400px",className:h="","data-testid":c,onFormatReady:m})=>{const[f,d]=t.useState(o),[g,u]=t.useState(null),[p,$]=t.useState(o);if(o!==p)if($(o),d(o),o.trim())try{JSON.parse(o),u(null)}catch(S){u(S.message)}else u(null);const b=t.useCallback(()=>{if(f.trim())try{const e=JSON.parse(f),t=JSON.stringify(e,null,2);d(t),r?.(t),u(null)}catch(S){u(S.message)}},[f,r]);t.useEffect(()=>{m&&m(b)},[m,b]);return e.jsxs(n,{className:h,$height:l,children:[e.jsx(i,{value:f,onChange:e=>{const t=e.target.value;d(t),(t=>{if(t.trim())try{JSON.parse(t),u(null)}catch(e){u(e.message)}else u(null)})(t),r?.(t)},onKeyDown:e=>{if("Tab"===e.key){e.preventDefault();const t=e.currentTarget,o=t.selectionStart,n=t.selectionEnd,i=f.substring(0,o)+"  "+f.substring(n);d(i),r?.(i),t.selectionStart=t.selectionEnd=o+2}},readOnly:a,spellCheck:!1,autoComplete:"off",autoCorrect:"off",autoCapitalize:"off","data-testid":c}),g&&e.jsxs(s,{children:["JSON Error: ",g]})]})};export{a as S};
