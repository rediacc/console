import{j as e,u as t}from"./chunk-DXoLy3RZ.js";import{R as a,r as s}from"./chunk-ZRs5Vi2W.js";import{d as i}from"./chunk-BtZST8U3.js";import{D as r,l as n,B as o,S as l,a as d,I as c}from"./chunk-B6OG5Vq-.js";import{u as m}from"./chunk-DLxZPlHK.js";import{T as p}from"../index-CEPyNj08.js";import{S as h}from"./chunk-D83A5xz1.js";import{u}from"./chunk-BYo3s0jF.js";const g=i.div`
  display: inline-flex;
  align-items: center;
  gap: ${({$gap:e,theme:t})=>t.spacing[e]}px;
`,x=i(o)`
  && {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    height: ${({theme:e})=>e.dimensions.CONTROL_HEIGHT_SM}px;
    border-radius: ${({theme:e})=>e.borderRadius.SM}px;
    ${({$hasLabel:e,theme:t})=>e?`\n      padding: 0 ${t.spacing.SM}px;\n      gap: ${t.spacing.XS}px;\n    `:`\n      width: ${t.dimensions.CONTROL_HEIGHT_SM}px;\n    `}
  }
`;function f({buttons:t,record:s,idField:i,testIdPrefix:o="",t:l,gap:d="SM"}){const c=s[i],m=String(null!=c?c:""),p=o?`${o}-`:"",h=t.filter(e=>void 0===e.visible||("boolean"==typeof e.visible?e.visible:e.visible(s))),u=e=>l?l(e):e;return e.jsx(g,{$gap:d,children:h.map((t,i)=>{if(function(e){return"custom"===e.type&&"render"in e}(t))return e.jsx(a.Fragment,{children:t.render(s)},`custom-${i}`);const o=!0===t.disabled||"function"==typeof t.disabled&&t.disabled(s),l=t.testIdSuffix?`${p}${t.testIdSuffix}-${m}`:`${p}${t.type}-${m}`,d=u(t.tooltip),c=t.ariaLabel?u(t.ariaLabel):d,h=t.label?u(t.label):void 0,g=e.jsx(x,{type:t.variant||"primary",size:"small",icon:t.icon,danger:t.danger,disabled:o,onClick:t.onClick?()=>t.onClick?.(s):void 0,"data-testid":l,"aria-label":c,$hasLabel:!!h,children:h});return t.dropdownItems?e.jsx(r,{menu:{items:t.dropdownItems,onClick:t.onDropdownClick?({key:e})=>t.onDropdownClick?.(e,s):void 0},trigger:["click"],children:e.jsx(n,{title:d,children:g})},t.type):e.jsx(n,{title:d,children:g},t.type)})})}function $(e,t){switch(t.type){case"INITIALIZE":return e.hasInitialized?e:{selectedTeams:t.teams,hasInitialized:!0};case"SET_TEAMS":return{...e,selectedTeams:t.teams};default:return e}}function b(e={}){const{autoSelect:a=!0,getInitialTeam:i}=e,{data:r,isLoading:n}=m(),o=s.useMemo(()=>r||[],[r]),l=t(e=>e.ui.uiMode),[d,c]=s.useReducer($,{selectedTeams:[],hasInitialized:!1});if(!n&&a&&o.length>0&&!d.hasInitialized){let e;if(i)e=i(o,l);else if("simple"===l){const t=o.find(e=>"Private Team"===e.teamName);e=t?.teamName||o[0].teamName}else e=o[0].teamName;c({type:"INITIALIZE",teams:[e]})}const p=s.useCallback(e=>{c({type:"SET_TEAMS",teams:e})},[]);return{teams:o,selectedTeams:d.selectedTeams,setSelectedTeams:p,isLoading:n,hasInitialized:d.hasInitialized}}const j=i(l)`
  && {
    width: 100%;

    .ant-select-selector {
      border-radius: ${({theme:e})=>e.borderRadius.MD}px !important;
      min-height: ${({theme:e})=>e.dimensions.CONTROL_HEIGHT}px;
    }
  }
`,y=i(d)`
  && {
    margin-right: ${({theme:e})=>e.spacing.XS}px;
    border-radius: ${({theme:e})=>e.borderRadius.SM}px;
    display: inline-flex;
    align-items: center;
    background-color: ${({theme:e})=>e.colors.primaryBg};
    color: ${({theme:e})=>e.colors.primary};
    border: 1px solid ${({theme:e})=>e.colors.primary};
  }
`,S=i.div`
  padding: ${({theme:e})=>e.spacing.SM}px;
`,T=i.div`
  border-top: 1px solid ${({theme:e})=>e.colors.borderSecondary};
`,I=i(c)`
  && {
    .ant-input-prefix {
      color: ${({theme:e})=>e.colors.textSecondary};
    }
  }
`,v=i.span`
  display: inline-flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.XS}px;
  color: ${({theme:e})=>e.colors.textPrimary};
`,C=i.span`
  display: inline-flex;
  align-items: center;
  color: ${({theme:e})=>e.colors.primary};
`,k=({teams:t,selectedTeams:a,onChange:i,loading:r=!1,placeholder:n="Select teams...",style:o})=>{const{t:l}=u("resources"),[d,c]=s.useState(""),m=s.useMemo(()=>t.filter(e=>e.teamName.toLowerCase().includes(d.toLowerCase())).map(t=>({label:e.jsxs(v,{children:[e.jsx(C,{children:e.jsx(p,{})}),e.jsx("span",{children:t.teamName})]}),value:t.teamName,"data-testid":`team-selector-option-${t.teamName}`})),[t,d]);return e.jsx(j,{mode:"multiple",style:o,placeholder:n,value:a,onChange:e=>i(e),loading:r,options:m,filterOption:!1,showSearch:!0,searchValue:d,onSearch:c,"data-testid":"team-selector",tagRender:t=>{const{value:a,closable:s,onClose:i}=t;return e.jsx(y,{closable:s,onClose:i,"data-testid":`team-selector-tag-${a}`,children:a})},popupRender:t=>e.jsxs(e.Fragment,{children:[e.jsx(S,{children:e.jsx(I,{placeholder:l("teams.placeholders.searchTeams"),prefix:e.jsx(h,{}),value:d,onChange:e=>c(e.target.value),onPressEnter:e=>e.stopPropagation(),autoComplete:"off","data-testid":"team-selector-search"})}),e.jsx(T,{children:t})]}),maxTagCount:"responsive",maxTagPlaceholder:t=>e.jsxs(y,{"data-testid":"team-selector-more-tag",children:["+",t.length," more"]})})};export{f as A,k as T,b as u};
