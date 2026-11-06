const {test}=require('node:test');
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {releaseBrowserOutputOnExit}=require('./badw_browser_process.cjs');

test('browser process closes even when a detached helper retains its pipes',async()=>{
 const child=spawn(process.execPath,['-e',`
  const {spawn}=require('node:child_process');
  const helper=spawn(process.execPath,['-e','setTimeout(()=>{},5000)'],
   {detached:true,stdio:['ignore',1,2]});
  helper.unref();
 `],{stdio:['ignore','pipe','pipe']});
 releaseBrowserOutputOnExit(child);
 await new Promise((resolve,reject)=>{
  const timer=setTimeout(()=>reject(new Error('inherited pipes delayed close')),3000);
  child.on('error',reject);
  child.on('close',code=>{clearTimeout(timer);try{assert.equal(code,0);resolve();}catch(e){reject(e);}});
 });
});
