// Keep the hashing implementation in the worker, off the page's UI thread.
export const MAX_LOCAL_BYTES=4*1024*1024*1024;
export function verificationTarget(target){
  if(!target||!['zip','image','archive'].includes(target.kind)||typeof target.name!=='string'||target.name.length<1||target.name.length>200||!Number.isSafeInteger(target.bytes)||target.bytes<0||target.bytes>MAX_LOCAL_BYTES||!/^[a-f0-9]{64}$/i.test(target.hash||''))throw new Error('此文件缺少有效的大小或 SHA256，无法进行网页校验。');
  return {name:target.name,bytes:target.bytes,hash:target.hash.toLowerCase(),kind:target.kind};
}
export async function verifyDownload(file,expected,{expectedSize,signal,onProgress=()=>{},workerFactory=()=>new Worker(new URL('./hash-worker.js?v=20261026-8',import.meta.url),{type:'module',name:'本机文件校验'})}={}){
  if(!/^[a-f0-9]{64}$/i.test(expected||''))throw new Error('此产物没有可用的 GitHub SHA256；请使用包内 SHA256SUMS 校验固件。');
  if(!file||!Number.isSafeInteger(file.size)||file.size<0||file.size>MAX_LOCAL_BYTES||typeof file.slice!=='function')throw new Error('请选择不超过 4 GiB 的本机文件。');
  if(expectedSize!==undefined&&(!Number.isSafeInteger(expectedSize)||expectedSize<0||file.size!==expectedSize))throw new Error('文件大小不符：请选择这一项对应的原始文件；ZIP 与解压后的映像不能混用。');
  if(signal?.aborted)throw new DOMException('已停止本机校验。','AbortError');
  return new Promise((resolve,reject)=>{
    let worker,settled=false,processed=0;
    const finish=(error,result)=>{if(settled)return;settled=true;signal?.removeEventListener('abort',abort);if(worker){worker.onmessage=null;worker.onerror=null;worker.onmessageerror=null;worker.terminate();}if(error)reject(error);else resolve(result);};
    const abort=()=>finish(new DOMException('已停止本机校验。','AbortError'));
    try{
      worker=workerFactory();
      worker.onmessage=({data})=>{
        if(settled)return;
        if(data?.type==='progress'&&Number.isSafeInteger(data.bytes)&&data.bytes>=processed&&data.bytes<=file.size&&data.total===file.size){processed=data.bytes;try{onProgress(processed,file.size);}catch{finish(new Error('本机校验显示中断，请重新选择文件后重试。'));}}
        else if(data?.type==='done'&&/^[a-f0-9]{64}$/.test(data.hash||'')&&data.bytes===file.size)finish(null,{hash:data.hash,ok:data.hash===expected.toLowerCase()});
        else finish(new Error('本机校验未完成，请重新选择文件后重试。'));
      };
      worker.onerror=worker.onmessageerror=event=>{event.preventDefault?.();finish(new Error('本机校验工具无法运行，请使用新版浏览器，或用系统 SHA256 工具核对。'));};
      signal?.addEventListener('abort',abort,{once:true});
      if(signal?.aborted){abort();return;}
      worker.postMessage({file});
    }catch{finish(new Error('本机校验工具无法运行，请使用新版浏览器，或用系统 SHA256 工具核对。'));}
  });
}
