import test from 'node:test';
import assert from 'node:assert/strict';
import {GitHub} from '../site/lib/github.js';

test('disconnect clears the session credential and aborts pending requests',async()=>{
  let pendingSignal;
  const git=new GitHub('owner/repo','fake-session-only','main',(_url,options)=>new Promise((_resolve,reject)=>{pendingSignal=options.signal;options.signal.addEventListener('abort',()=>reject(new DOMException('aborted','AbortError')),{once:true});}));
  const pending=git.runs();git.close();
  assert.equal(git.token,'');assert.equal(pendingSignal.aborted,true);await assert.rejects(pending,/授权已断开/);
  await assert.rejects(()=>git.runs(),/授权已断开/);git.close();
});
test('late response from an aborted session cannot restore private results',async()=>{
  let resolve;
  const git=new GitHub('owner/repo','fake-session-only','main',()=>new Promise(r=>resolve=r));
  const pending=git.runs();git.close();resolve({ok:true,status:200,json:async()=>({workflow_runs:[{id:123}]})});
  await assert.rejects(pending,/不会载入旧会话/);
});
test('disconnect during JSON decoding discards a late private response',async()=>{
  let resolve;let started;
  const decoding=new Promise(r=>started=r);
  const git=new GitHub('owner/repo','fake-session-only','main',async()=>({ok:true,status:200,json:()=>{started();return new Promise(r=>resolve=r);}}));
  const pending=git.runs();await decoding;git.close();resolve({workflow_runs:[{id:123}]});await assert.rejects(pending,/不会载入旧会话/);
});
test('disconnect is local only and does not revoke tokens or cancel GitHub jobs',async()=>{
  const calls=[];const git=new GitHub('owner/repo','fake-session-only','main',async(url,options)=>{calls.push({url,options});return {ok:true,status:200,json:async()=>({private:true})};});
  await git.connect();git.close();assert.equal(calls.length,1);assert.equal(calls[0].options.method,undefined);
});
