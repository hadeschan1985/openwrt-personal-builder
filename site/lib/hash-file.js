import {sha256} from '../vendor/noble-hashes-2.4.0/sha2.js';

export const CHUNK_BYTES=1024*1024;
export const MAX_LOCAL_BYTES=4*1024*1024*1024;
export function validateLocalFile(file){
  if(!file||!Number.isSafeInteger(file.size)||file.size<0||file.size>MAX_LOCAL_BYTES||typeof file.slice!=='function')throw new Error('请选择不超过 4 GiB 的本机文件。');
}
// Runs in a dedicated worker. Never reads a whole firmware into memory.
export async function hashFile(file,{onProgress=()=>{},signal}={}){
  validateLocalFile(file);
  const hash=sha256.create();
  const abort=()=>{if(signal?.aborted)throw new DOMException('已停止本机校验。','AbortError');};
  let bytes=0,lastUpdate=0;
  try{
    abort();onProgress(0,file.size);
    while(bytes<file.size){
      abort();
      const end=Math.min(bytes+CHUNK_BYTES,file.size);
      const block=new Uint8Array(await file.slice(bytes,end).arrayBuffer());
      abort();
      if(block.byteLength!==end-bytes)throw new Error('本机文件读取不完整，请重新选择文件。');
      hash.update(block);bytes=end;
      const now=Date.now();if(now-lastUpdate>=100||bytes===file.size){onProgress(bytes,file.size);lastUpdate=now;}
    }
    abort();
    return Array.from(hash.digest(),n=>n.toString(16).padStart(2,'0')).join('');
  }finally{hash.destroy();}
}
