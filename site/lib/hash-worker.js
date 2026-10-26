import {hashFile} from './hash-file.js?v=20261026-8';

// Receives only the chosen local File; no GitHub token, URL or network request.
self.onmessage=async event=>{
  try{
    const file=event.data.file;
    const hash=await hashFile(file,{onProgress:(bytes,total)=>self.postMessage({type:'progress',bytes,total})});
    self.postMessage({type:'done',hash,bytes:file.size});
  }catch{self.postMessage({type:'error'});}
};
