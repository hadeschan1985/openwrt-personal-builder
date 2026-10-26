import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash,randomBytes} from 'node:crypto';
import {readFile} from 'node:fs/promises';
import {Worker} from 'node:worker_threads';
import {hashFile,CHUNK_BYTES} from '../site/lib/hash-file.js';
import {verifyDownload,verificationTarget,MAX_LOCAL_BYTES} from '../site/lib/verification.js';

const digest=bytes=>createHash('sha256').update(bytes).digest('hex');
function realWorker(){
  const node=new Worker(new URL('./fixtures/hash-worker-node.mjs',import.meta.url));
  const wrapper={postMessage:data=>node.postMessage(data),terminate:()=>node.terminate()};
  node.on('message',data=>wrapper.onmessage?.({data}));node.on('error',error=>wrapper.onerror?.({preventDefault(){},error}));
  return wrapper;
}
test('pinned hashing dependency preserves all upstream bytes and MIT license',async()=>{
  const base=new URL('../site/vendor/noble-hashes-2.4.0/',import.meta.url),source=JSON.parse(await readFile(new URL('SOURCE.json',base),'utf8'));
  for(const [name,expected] of Object.entries(source.files_sha256))assert.equal(digest(await readFile(new URL(name,base))),expected,name);
  assert.match(await readFile(new URL('LICENSE',base),'utf8'),/MIT License/);
});
test('incremental hash matches independent native SHA256 across padding and chunk boundaries',async()=>{
  for(const size of [0,1,55,56,63,64,65,119,120,127,128,CHUNK_BYTES-1,CHUNK_BYTES,CHUNK_BYTES+1,2*CHUNK_BYTES+123]){
    const bytes=randomBytes(size);assert.equal(await hashFile(new Blob([bytes])),digest(bytes),String(size));
  }
});
test('over 256 MiB is hashed with reads bounded to one MiB and never a whole-file read',async()=>{
  const size=257*1024*1024+17,block=Buffer.alloc(CHUNK_BYTES,0x5a),native=createHash('sha256');let reads=0,last=0;
  const file={size,arrayBuffer(){throw Error('whole-file read forbidden');},slice(start,end){assert.ok(end-start<=CHUNK_BYTES);assert.equal(start,last);last=end;reads++;return new Blob([block.subarray(0,end-start)]);}};
  for(let left=size;left>0;left-=CHUNK_BYTES)native.update(block.subarray(0,Math.min(left,CHUNK_BYTES)));
  const progress=[];assert.equal(await hashFile(file,{onProgress:(done,total)=>{progress.push(done);assert.equal(total,size);}}),native.digest('hex'));
  assert.equal(last,size);assert.equal(reads,258);assert.equal(progress[0],0);assert.equal(progress.at(-1),size);assert.ok(progress.every((n,i)=>!i||n>=progress[i-1]));
});
test('invalid, truncated and cancelled file reads never produce a successful digest',async()=>{
  await assert.rejects(hashFile({size:MAX_LOCAL_BYTES+1,slice(){throw Error('must not read');}}),/4 GiB/);
  await assert.rejects(hashFile({size:3,slice:()=>new Blob(['a'])}),/不完整/);
  const controller=new AbortController();let reads=0;
  const file={size:2*CHUNK_BYTES,slice(){reads++;return {arrayBuffer:async()=>{controller.abort();return new ArrayBuffer(CHUNK_BYTES);}};}};
  await assert.rejects(hashFile(file,{signal:controller.signal}),e=>e.name==='AbortError');assert.equal(reads,1);
});
test('actual background worker verifies correct bytes and rejects a same-size corruption',async()=>{
  const bytes=randomBytes(3*CHUNK_BYTES+7),expected=digest(bytes),file=new Blob([bytes]);let progress=0;
  const result=await verifyDownload(file,expected.toUpperCase(),{workerFactory:realWorker,expectedSize:file.size,onProgress:n=>progress=n});
  assert.deepEqual(result,{hash:expected,ok:true});assert.equal(progress,file.size);
  bytes[99]^=1;assert.equal((await verifyDownload(new Blob([bytes]),expected,{workerFactory:realWorker})).ok,false);
});
test('wrong file size, invalid metadata and pre-cancellation cannot read a file or create a worker',async()=>{
  const file=new Blob(['abc']),expected=digest('abc'),workerFactory=()=>{throw Error('must not create worker');};
  await assert.rejects(verifyDownload(file,expected,{expectedSize:4,workerFactory}),/大小不符/);
  const controller=new AbortController();controller.abort();await assert.rejects(verifyDownload(file,expected,{signal:controller.signal,workerFactory}),e=>e.name==='AbortError');
  const target={name:'image.img.gz',bytes:3,hash:expected,kind:'image'};assert.deepEqual(verificationTarget(target),target);
  for(const invalid of [{...target,bytes:-1},{...target,bytes:NaN},{...target,hash:'bad'},{...target,kind:'unknown'},{...target,bytes:MAX_LOCAL_BYTES+1}])assert.throws(()=>verificationTarget(invalid),/有效/);
});
test('cancellation terminates worker, drops chosen file handlers and ignores late completion',async()=>{
  let worker,terminated=0,sent;const controller=new AbortController(),expected=digest('abc');
  const result=verifyDownload(new Blob(['abc']),expected,{signal:controller.signal,workerFactory:()=>worker={postMessage:data=>sent=data,terminate:()=>terminated++}});
  const late=worker.onmessage;controller.abort();await assert.rejects(result,e=>e.name==='AbortError');
  late({data:{type:'done',hash:expected,bytes:3}});assert.equal(terminated,1);assert.equal(worker.onmessage,null);assert.deepEqual(Object.keys(sent),['file']);
});
test('worker setup and malformed replies fail safely without exposing raw errors',async()=>{
  const file=new Blob(['abc']),expected=digest('abc');
  await assert.rejects(verifyDownload(file,expected,{workerFactory:()=>{throw Error('private raw error');}}),e=>/无法运行/.test(e.message)&&!e.message.includes('private'));
  let worker,terminated=0;const result=verifyDownload(file,expected,{workerFactory:()=>worker={postMessage(){},terminate:()=>terminated++}});
  worker.onmessage({data:{type:'done',hash:expected,bytes:2}});await assert.rejects(result,/未完成/);assert.equal(terminated,1);
});
