import{j as e}from"./chunk-jIVxg-O4.js";import{r as a}from"./chunk-DaihG_v-.js";import{T as r}from"../index-pYX32kNS.js";import{S as t}from"./chunk-B5MW1YpM.js";import{d as o}from"./chunk-CsUqxJyM.js";import{S as s,a as l,I as i}from"./chunk-DcGI-zRP.js";import{u as n}from"./chunk-DfOmacDz.js";const m=o(s)`
  && {
    width: 100%;

    .ant-select-selector {
      border-radius: ${({theme:e})=>e.borderRadius.MD}px !important;
      min-height: ${({theme:e})=>e.dimensions.CONTROL_HEIGHT}px;
    }
  }
`,c=o(l)`
  && {
    margin-right: ${({theme:e})=>e.spacing.XS}px;
    border-radius: ${({theme:e})=>e.borderRadius.SM}px;
    display: inline-flex;
    align-items: center;
    background-color: ${({theme:e})=>e.colors.primaryBg};
    color: ${({theme:e})=>e.colors.primary};
    border: 1px solid ${({theme:e})=>e.colors.primary};
  }
`,d=o.div`
  padding: ${({theme:e})=>e.spacing.SM}px;
`,p=o.div`
  border-top: 1px solid ${({theme:e})=>e.colors.borderSecondary};
`,h=o(i)`
  && {
    .ant-input-prefix {
      color: ${({theme:e})=>e.colors.textSecondary};
    }
  }
`,x=o.span`
  display: inline-flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.XS}px;
  color: ${({theme:e})=>e.colors.textPrimary};
`,u=o.span`
  display: inline-flex;
  align-items: center;
  color: ${({theme:e})=>e.colors.primary};
`,g=({teams:o,selectedTeams:s,onChange:l,loading:i=!1,placeholder:g="Select teams...",style:j})=>{const{t:f}=n("resources"),[$,y]=a.useState(""),S=a.useMemo(()=>o.filter(e=>e.teamName.toLowerCase().includes($.toLowerCase())).map(a=>({label:e.jsxs(x,{children:[e.jsx(u,{children:e.jsx(r,{})}),e.jsx("span",{children:a.teamName})]}),value:a.teamName,"data-testid":`team-selector-option-${a.teamName}`})),[o,$]);return e.jsx(m,{mode:"multiple",style:j,placeholder:g,value:s,onChange:e=>l(e),loading:i,options:S,filterOption:!1,showSearch:!0,searchValue:$,onSearch:y,"data-testid":"team-selector",tagRender:a=>{const{value:r,closable:t,onClose:o}=a;return e.jsx(c,{closable:t,onClose:o,"data-testid":`team-selector-tag-${r}`,children:r})},popupRender:a=>e.jsxs(e.Fragment,{children:[e.jsx(d,{children:e.jsx(h,{placeholder:f("teams.placeholders.searchTeams"),prefix:e.jsx(t,{}),value:$,onChange:e=>y(e.target.value),onPressEnter:e=>e.stopPropagation(),autoComplete:"off","data-testid":"team-selector-search"})}),e.jsx(p,{children:a})]}),maxTagCount:"responsive",maxTagPlaceholder:a=>e.jsxs(c,{"data-testid":"team-selector-more-tag",children:["+",a.length," more"]})})};export{g as T};
