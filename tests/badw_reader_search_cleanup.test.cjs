const {test}=require('node:test');
const assert=require('node:assert/strict');
const {validateSearch}=require('./badw_reader_search.browser.cjs');

test('search releases its browser context when page creation fails',async()=>{
 const failure=new Error('page creation failed');
 let closed=0;
 const browser={newContext:async()=>({
  newPage:async()=>{throw failure;},
  close:async()=>{closed++;}
 })};
 await assert.rejects(validateSearch(browser,'http://unused',[]),e=>e===failure);
 assert.equal(closed,1);
});
