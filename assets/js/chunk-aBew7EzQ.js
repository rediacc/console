import{b as e}from"./chunk-Dx23Oqz1.js";import{g as a,j as t}from"./chunk-BcoMUYMA.js";import{B as s,d as r,ai as o,g as i,aj as l,I as n,T as m}from"../index-ClLYmVcU.js";import{S as d}from"./chunk-CrAvvfvb.js";import{u as c}from"./chunk-DsYhoPUY.js";function h(e,a){switch(a.type){case"INITIALIZE":return e.hasInitialized?e:{selectedTeams:a.teams,hasInitialized:!0};case"SET_TEAMS":return{...e,selectedTeams:a.teams};default:return e}}function p(t={}){const{autoSelect:r=!0,getInitialTeam:o}=t,{data:i,isLoading:l}=s(),n=e.useMemo(()=>i||[],[i]),m=a(e=>e.ui.uiMode),[d,c]=e.useReducer(h,{selectedTeams:[],hasInitialized:!1});if(!l&&r&&n.length>0&&!d.hasInitialized){let e;if(o)e=o(n,m);else if("simple"===m){const a=n.find(e=>"Private Team"===e.teamName);e=a?.teamName||n[0].teamName}else e=n[0].teamName;c({type:"INITIALIZE",teams:[e]})}const p=e.useCallback(e=>{c({type:"SET_TEAMS",teams:e})},[]);return{teams:n,selectedTeams:d.selectedTeams,setSelectedTeams:p,isLoading:l,hasInitialized:d.hasInitialized}}const u=r(o).attrs({fullWidth:!0})`
  && .ant-select-selector {
    border-radius: ${({theme:e})=>e.borderRadius.MD}px;
  }
`,g=r(i).attrs({preset:"team"})`
  && {
    margin-right: ${({theme:e})=>e.spacing.XS}px;
    border-radius: ${({theme:e})=>e.borderRadius.SM}px;
    display: inline-flex;
    align-items: center;
    padding: ${({theme:e})=>e.spacing.XS}px;
  }
`,x=r.div`
  padding: ${({theme:e})=>e.spacing.SM}px;
`,f=r.div`
  border-top: 1px solid ${({theme:e})=>e.colors.borderSecondary};
`,T=r(l)`
  && {
    .ant-input-prefix {
      color: ${({theme:e})=>e.colors.textSecondary};
    }
  }
`,j=r(n)`
  color: ${({theme:e})=>e.colors.textPrimary};
`,S=r(n)`
  color: ${({theme:e})=>e.colors.primary};
`,I=({teams:a,selectedTeams:s,onChange:r,loading:o=!1,placeholder:i="Select teams...",style:l})=>{const{t:n}=c("resources"),[h,p]=e.useState(""),I=e.useMemo(()=>a.filter(e=>e.teamName.toLowerCase().includes(h.toLowerCase())).map(e=>({label:t.jsxs(j,{children:[t.jsx(S,{children:t.jsx(m,{})}),t.jsx("span",{children:e.teamName})]}),value:e.teamName,"data-testid":`team-selector-option-${e.teamName}`})),[a,h]);return t.jsx(u,{mode:"multiple",style:l,placeholder:i,value:s,onChange:e=>r(e),loading:o,options:I,filterOption:!1,showSearch:!0,searchValue:h,onSearch:p,"data-testid":"team-selector",tagRender:e=>{const{value:a,closable:s,onClose:r}=e;return t.jsx(g,{closable:s,onClose:r,"data-testid":`team-selector-tag-${a}`,children:a})},dropdownRender:e=>t.jsxs(t.Fragment,{children:[t.jsx(x,{children:t.jsx(T,{placeholder:n("teams.placeholders.searchTeams"),prefix:t.jsx(d,{}),value:h,onChange:e=>p(e.target.value),onPressEnter:e=>e.stopPropagation(),autoComplete:"off","data-testid":"team-selector-search"})}),t.jsx(f,{children:e})]}),maxTagCount:"responsive",maxTagPlaceholder:e=>t.jsxs(g,{"data-testid":"team-selector-more-tag",children:["+",e.length," more"]})})};export{I as T,p as u};
