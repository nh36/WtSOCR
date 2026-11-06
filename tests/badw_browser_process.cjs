// Chrome helpers may inherit its output pipes and outlive the browser itself.
// Release only these pipes, only after the owned browser process has exited.
function releaseBrowserOutputOnExit(child){
 child.once('exit',()=>{child.stdout?.destroy();child.stderr?.destroy();});
}

async function launchTestBrowser(chromium,options){
 const server=await chromium.launchServer({...options,host:'127.0.0.1'});
 releaseBrowserOutputOnExit(server.process());
 let browser;
 try{browser=await chromium.connect(server.wsEndpoint());}
 catch(error){await server.close();throw error;}
 return {browser,closeBrowser:async()=>{
  try{await browser.close();}finally{await server.close();}
 }};
}
module.exports={launchTestBrowser,releaseBrowserOutputOnExit};
