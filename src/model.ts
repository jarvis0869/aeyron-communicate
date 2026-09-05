export type Mode = 'speak' | 'type' | 'notebook' | 'resources';
export type DraftState = {original:string; draft:string; suggestion:string|null; approved:string|null; revision:number; warnings:string[]};
export const emptyDraft:DraftState={original:'',draft:'',suggestion:null,approved:null,revision:0,warnings:[]};
export type Action = {type:'input';text:string}|{type:'edit';text:string}|{type:'suggestion';text:string;warnings:string[];revision:number}|{type:'useSuggestion'}|{type:'undo'}|{type:'approve'}|{type:'clear'};
export function draftReducer(s:DraftState,a:Action):DraftState {
  switch(a.type){
    case 'input':return {...emptyDraft,original:a.text,draft:a.text,revision:s.revision+1};
    case 'edit':return {...s,draft:a.text,approved:null,suggestion:null,warnings:[],revision:s.revision+1};
    case 'suggestion':return a.revision!==s.revision?s:{...s,suggestion:a.text,warnings:a.warnings,approved:null};
    case 'useSuggestion':return s.suggestion===null?s:{...s,draft:s.suggestion,suggestion:null,approved:null,revision:s.revision+1};
    case 'undo':return {...s,draft:s.original,suggestion:null,approved:null,warnings:[],revision:s.revision+1};
    case 'approve':return s.draft.trim()?{...s,approved:s.draft}:s;
    case 'clear':return {...emptyDraft,revision:s.revision+1};
  }
}
export type Entry={id:string;text:string;createdAt:string};
export const NOTEBOOK_KEY='aeyron.notebook.v1';
export const MAX_ENTRIES=100;
export function randomId():string{
  const cryptoApi=globalThis.crypto;
  if(cryptoApi?.randomUUID)return cryptoApi.randomUUID();
  if(cryptoApi?.getRandomValues){const bytes=new Uint8Array(16);cryptoApi.getRandomValues(bytes);bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;const hex=Array.from(bytes,b=>b.toString(16).padStart(2,'0')).join('');return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;}
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}
export function decodeNotebook(raw:string|null):Entry[]{
  if(!raw)return [];
  const parsed:unknown=JSON.parse(raw);
  if(!Array.isArray(parsed)||parsed.length>MAX_ENTRIES)throw new Error('Notebook format is not supported.');
  if(!parsed.every(e=>e&&typeof e.id==='string'&&typeof e.text==='string'&&e.text.length<=4000&&typeof e.createdAt==='string'&&Number.isFinite(Date.parse(e.createdAt))))throw new Error('Notebook data could not be read.');
  return parsed;
}
export function readNotebook():Entry[]{return decodeNotebook(localStorage.getItem(NOTEBOOK_KEY));}
export function writeNotebook(entries:Entry[]):void{if(entries.length>MAX_ENTRIES)throw new Error('Notebook is full. Export or delete some entries.');localStorage.setItem(NOTEBOOK_KEY,JSON.stringify(entries));}
export const externalResources={parkibot:'https://parkibot.com/'} as const;
