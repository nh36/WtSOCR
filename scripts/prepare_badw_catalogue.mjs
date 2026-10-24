/** Offline catalogue preparation. No entry bodies or network access required. */
import {compare} from './vendor/tibetan-sort-js/index.mjs';
import {createRequire} from 'node:module';
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
const {entrySearchKeys}=createRequire(import.meta.url)('./badw_dictionary_prototype/app.js');

export const ordering='Tibetan headword order (BDRC 2.3.1; WTS wa-zur convention), then numeric homonym and source identity. Unavailable or unsupported Tibetan keys follow in deterministic LoC order; all remain searchable.';
// Native stacks from WTS I, printed p. xxi. This is an eligibility check,
// not a replacement collation algorithm. Wa zur is checked separately.
const stacks=new Set(('ཀྱ ཀྲ ཀླ ཁྱ ཁྲ གྱ གྲ གླ རྐ རྐྱ ལྐ སྐ སྐྱ སྐྲ '+
 'རྒ རྒྱ ལྒ སྒ སྒྱ སྒྲ རྔ ལྔ སྔ ལྕ རྗ ལྗ རྙ སྙ '+
 'ཏྲ རྟ ལྟ སྟ ཐྲ དྲ རྡ ལྡ སྡ རྣ སྣ སྣྲ པྱ པྲ ལྤ སྤ སྤྱ སྤྲ '+
 'ཕྱ ཕྲ བྱ བྲ བླ རྦ ལྦ སྦ སྦྱ སྦྲ མྱ རྨ རྨྱ སྨ སྨྱ སྨྲ '+
 'རྩ སྩ རྫ ཟླ རླ ལྷ ཤྲ སྲ སླ ཧྲ').split(' '));
const native=/^[ཀཁགངཅཆཇཉཏཐདནཔཕབམཙཚཛཝཞཟའཡརལཤསཧཨ\u0f90-\u0fbcིེོུ་]+$/u;
export function tibetanKey(value){
 if(typeof value!=='string'||!value.trim())return {reason:'missing_tibetan'};
 // Only key punctuation is regularized; source strings are untouched.
 const key=value.normalize('NFC').trim().replace(/[་།༎\s]+$/u,'');
 if(/[^\u0f00-\u0fff]/u.test(key))return {reason:'mixed_or_non_tibetan'};
 if(!key||!native.test(key))return {reason:'unsupported_characters'};
 const plain=key.replaceAll('ྭ','');
 for(const match of plain.matchAll(/[\u0f40-\u0f6c][\u0f90-\u0fbc]+/gu)){
  if(!stacks.has(match[0]))return {reason:'unsupported_stack'};
  const syllableStart=plain.lastIndexOf('་',match.index-1)+1;
  const prefix=plain.slice(syllableStart,match.index);
  if(prefix&&!/^[གདབམའ]$/u.test(prefix))return {reason:'unsupported_stack'};
 }
 if(/(^|་)[\u0f90-\u0fbcིེོུ]/u.test(key))return {reason:'malformed_syllable'};
 return {key,plain};
}
const lexical=(a,b)=>a<b?-1:a>b?1:0;
function homonym(value){
 // Missing numbers precede numbered homonyms; unexpected labels are retained.
 const s=String(value??'');return /^\d+$/.test(s)?[1,BigInt(s),s]:[s?2:0,0n,s];
}
function compareHomonyms(a,b){return a[0]-b[0]||(a[1]<b[1]?-1:a[1]>b[1]?1:0)||(a[0]===2?lexical(a[2],b[2]):0);}
export function prepareCatalogue(entries){
 const started=performance.now(),reasons={};
 const decorated=entries.map(entry=>{
  const key=tibetanKey(entry.headword?.tibetan);
  if(key.reason)reasons[key.reason]=(reasons[key.reason]||0)+1;
  const {collation_fallback:_old,search_keys:_keys,...source}=entry;
  return {entry:{...source,search_keys:entrySearchKeys(source),...(key.reason?{collation_fallback:key.reason}:{})},...key,
   fallback:String(entry.headword?.loc||'').normalize('NFC'),homonym:homonym(entry.homonym)};
 });
 decorated.sort((a,b)=>Number(!!a.reason)-Number(!!b.reason)||
  (a.reason?lexical(a.fallback,b.fallback):compare(a.plain,b.plain)||compare(a.key,b.key))||
  compareHomonyms(a.homonym,b.homonym)||lexical(a.entry.source_kind||'',b.entry.source_kind||'')||lexical(a.entry.id,b.entry.id));
 const fallback=Object.values(reasons).reduce((a,b)=>a+b,0);
 return {entries:decorated.map(e=>e.entry),ordering,collation:{library:'@buda-base/tibetan-sort',version:'2.3.1',
  commit:'6c664f5be95aa4c6684fb08fb7aeab30cfb80fe3',keyed:entries.length-fallback,fallback,reasons,
  seconds:(performance.now()-started)/1000}};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 const input=JSON.parse(readFileSync(0,'utf8'));
 process.stdout.write(JSON.stringify(prepareCatalogue(input)));
}
