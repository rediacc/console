import{j as e,g as a}from"./chunk-DafPgHWS.js";import{b as t}from"./chunk-DV57Chae.js";import{S as s}from"./chunk-OuU-RzcS.js";import{d as r,ar as o,f as i,bt as l,I as n,T as m}from"../index-VtVQDmDS.js";import{u as d}from"./chunk-BtSyf1HU.js";import{u as c}from"./chunk-DLifTvLG.js";const h=r(o).attrs({fullWidth:!0})`
  && .ant-select-selector {
    border-radius: ${({theme:e})=>e.borderRadius.MD}px;
  }
`,p=r(i).attrs({preset:"team"})`
  && {
    margin-right: ${({theme:e})=>e.spacing.XS}px;
    border-radius: ${({theme:e})=>e.borderRadius.SM}px;
    display: inline-flex;
    align-items: center;
    padding: 2px 4px;
  }
`,u=r.div`
  padding: ${({theme:e})=>e.spacing.SM}px;
`,x=r.div`
  border-top: 1px solid ${({theme:e})=>e.colors.borderSecondary};
`,g=r(l)`
  && {
    .ant-input-prefix {
      color: ${({theme:e})=>e.colors.textSecondary};
    }
  }
`,f=r(n)`
  color: ${({theme:e})=>e.colors.textPrimary};
`,T=r(n)`
  color: ${({theme:e})=>e.colors.primary};
`,j=({teams:a,selectedTeams:r,onChange:o,loading:i=!1,placeholder:l="Select teams...",style:n})=>{const{t:c}=d("resources"),[j,I]=t.useState(""),S=t.useMemo(()=>a.filter(e=>e.teamName.toLowerCase().includes(j.toLowerCase())).map(a=>({label:e.jsxs(f,{children:[e.jsx(T,{children:e.jsx(m,{})}),e.jsx("span",{children:a.teamName})]}),value:a.teamName,"data-testid":`team-selector-option-${a.teamName}`})),[a,j]);return e.jsx(h,{mode:"multiple",size:"sm",style:n,placeholder:l,value:r,onChange:e=>o(e),loading:i,options:S,filterOption:!1,showSearch:!0,searchValue:j,onSearch:I,"data-testid":"team-selector",tagRender:a=>{const{value:t,closable:s,onClose:r}=a;return e.jsx(p,{closable:s,onClose:r,"data-testid":`team-selector-tag-${t}`,children:t})},dropdownRender:a=>e.jsxs(e.Fragment,{children:[e.jsx(u,{children:e.jsx(g,{placeholder:c("teams.placeholders.searchTeams"),prefix:e.jsx(s,{}),value:j,onChange:e=>I(e.target.value),onPressEnter:e=>e.stopPropagation(),autoComplete:"off","data-testid":"team-selector-search"})}),e.jsx(x,{children:a})]}),maxTagCount:"responsive",maxTagPlaceholder:a=>e.jsxs(p,{"data-testid":"team-selector-more-tag",children:["+",a.length," more"]})})};function I(e,a){switch(a.type){case"INITIALIZE":return e.hasInitialized?e:{selectedTeams:a.teams,hasInitialized:!0};case"SET_TEAMS":return{...e,selectedTeams:a.teams};default:return e}}function S(e={}){const{autoSelect:s=!0,getInitialTeam:r}=e,{data:o,isLoading:i}=c(),l=t.useMemo(()=>o||[],[o]),n=a(e=>e.ui.uiMode),[m,d]=t.useReducer(I,{selectedTeams:[],hasInitialized:!1});if(!i&&s&&l.length>0&&!m.hasInitialized){let e;if(r)e=r(l,n);else if("simple"===n){const a=l.find(e=>"Private Team"===e.teamName);e=a?.teamName||l[0].teamName}else e=l[0].teamName;d({type:"INITIALIZE",teams:[e]})}const h=t.useCallback(e=>{d({type:"SET_TEAMS",teams:e})},[]);return{teams:l,selectedTeams:m.selectedTeams,setSelectedTeams:h,isLoading:i,hasInitialized:m.hasInitialized}}export{j as T,S as u};
