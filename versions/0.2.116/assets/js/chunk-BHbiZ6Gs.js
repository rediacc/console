import{j as o}from"./chunk-DH1Qig9d.js";import{s as r,w as s}from"./chunk-CceKb867.js";import{c as e,f as c,d as n}from"../index-ClTVN05S.js";const a=n(c)`
  && {
    border-radius: ${({theme:o})=>o.borderRadius.SM}px;
    border-color: ${({theme:o})=>o.colors.info};
    color: ${({theme:o})=>o.colors.info};
    background: ${({theme:o})=>o.colors.bgPrimary};
  }
`;n.span`
  font-family: monospace;
  font-size: 12px;
  color: var(--color-text-secondary);
`;const t=(o,s="YYYY-MM-DD HH:mm:ss")=>o?r(o).format(s):"-",l=(s,c="YYYY-MM-DD HH:mm:ss")=>s?r(s).format(c):o.jsx(e,{color:"secondary",children:"-"}),i=(r,e={color:"default"})=>function(c){const n=r[c]||e;return o.jsx(s,{title:n.label||c,children:o.jsx("span",{style:{fontSize:"16px",cursor:"pointer"},children:n.icon})})},m=(r,s="Yes",n="No")=>null==r?o.jsx(e,{color:"secondary",children:"-"}):r?o.jsx(c,{variant:"success",children:s}):o.jsx(c,{children:n});export{a as V,t as a,l as b,i as c,m as r};
