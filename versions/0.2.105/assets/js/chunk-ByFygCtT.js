import{b as e}from"./chunk-DDwtzQW6.js";import{u as a,j as t}from"./chunk-DUi8bg1D.js";import{u as s}from"./chunk-Bqnq7YJr.js";import{d as r,T as o}from"../index-DldRJJRQ.js";import{S as i}from"./chunk-DEO1aopL.js";import{a as l,d as n,I as m}from"./chunk-CX_EivFx.js";import{u as c}from"./chunk-BQNjmpVv.js";function d(e,a){switch(a.type){case"INITIALIZE":return e.hasInitialized?e:{selectedTeams:a.teams,hasInitialized:!0};case"SET_TEAMS":return{...e,selectedTeams:a.teams};default:return e}}function p(t={}){const{autoSelect:r=!0,getInitialTeam:o}=t,{data:i,isLoading:l}=s(),n=e.useMemo(()=>i||[],[i]),m=a(e=>e.ui.uiMode),[c,p]=e.useReducer(d,{selectedTeams:[],hasInitialized:!1});if(!l&&r&&n.length>0&&!c.hasInitialized){let e;if(o)e=o(n,m);else if("simple"===m){const a=n.find(e=>"Private Team"===e.teamName);e=a?.teamName||n[0].teamName}else e=n[0].teamName;p({type:"INITIALIZE",teams:[e]})}const h=e.useCallback(e=>{p({type:"SET_TEAMS",teams:e})},[]);return{teams:n,selectedTeams:c.selectedTeams,setSelectedTeams:h,isLoading:l,hasInitialized:c.hasInitialized}}const h=r(l)`
  && {
    width: 100%;
  }

  && .ant-select-selector {
    border-radius: ${({theme:e})=>e.borderRadius.MD}px;
    min-height: ${({theme:e})=>e.dimensions.CONTROL_HEIGHT}px;
  }
`,u=r(n)`
  && {
    margin-right: ${({theme:e})=>e.spacing.XS}px;
    border-radius: ${({theme:e})=>e.borderRadius.SM}px;
    display: inline-flex;
    align-items: center;
    background-color: ${({theme:e})=>e.colors.primaryBg};
    color: ${({theme:e})=>e.colors.primary};
    border: 1px solid ${({theme:e})=>e.colors.primary};
  }
`,g=r.div`
  padding: ${({theme:e})=>e.spacing.SM}px;
`,x=r.div`
  border-top: 1px solid ${({theme:e})=>e.colors.borderSecondary};
`,f=r(m)`
  && {
    .ant-input-prefix {
      color: ${({theme:e})=>e.colors.textSecondary};
    }
  }
`,T=r.span`
  display: inline-flex;
  align-items: center;
  gap: ${({theme:e})=>e.spacing.XS}px;
  color: ${({theme:e})=>e.colors.textPrimary};
`,j=r.span`
  display: inline-flex;
  align-items: center;
  color: ${({theme:e})=>e.colors.primary};
`,I=({teams:a,selectedTeams:s,onChange:r,loading:l=!1,placeholder:n="Select teams...",style:m})=>{const{t:d}=c("resources"),[p,I]=e.useState(""),S=e.useMemo(()=>a.filter(e=>e.teamName.toLowerCase().includes(p.toLowerCase())).map(e=>({label:t.jsxs(T,{children:[t.jsx(j,{children:t.jsx(o,{})}),t.jsx("span",{children:e.teamName})]}),value:e.teamName,"data-testid":`team-selector-option-${e.teamName}`})),[a,p]);return t.jsx(h,{mode:"multiple",style:m,placeholder:n,value:s,onChange:e=>r(e),loading:l,options:S,filterOption:!1,showSearch:!0,searchValue:p,onSearch:I,"data-testid":"team-selector",tagRender:e=>{const{value:a,closable:s,onClose:r}=e;return t.jsx(u,{closable:s,onClose:r,"data-testid":`team-selector-tag-${a}`,children:a})},popupRender:e=>t.jsxs(t.Fragment,{children:[t.jsx(g,{children:t.jsx(f,{placeholder:d("teams.placeholders.searchTeams"),prefix:t.jsx(i,{}),value:p,onChange:e=>I(e.target.value),onPressEnter:e=>e.stopPropagation(),autoComplete:"off","data-testid":"team-selector-search"})}),t.jsx(x,{children:e})]}),maxTagCount:"responsive",maxTagPlaceholder:e=>t.jsxs(u,{"data-testid":"team-selector-more-tag",children:["+",e.length," more"]})})};export{I as T,p as u};
