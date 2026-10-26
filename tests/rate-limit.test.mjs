import test from 'node:test';
import assert from 'node:assert/strict';
import {GitHub} from '../site/lib/github.js';

function response(status,headers={},message=''){return {ok:status===200,status,headers:new Headers(headers),json:async()=>({message})};}
test('expired authorization clears the credential and stops later reads',async()=>{
  let calls=0;const git=new GitHub('owner/repo','test-only','main',async()=>{calls++;return response(401);});
  await assert.rejects(()=>git.runs(),e=>e.status===401);assert.equal(git.token,'');assert.equal(git.canQuery,false);assert.equal(git.pollDelay,Infinity);
  await assert.rejects(()=>git.runs(),/重新连接/);assert.equal(calls,1);
});
test('permission errors pause polling without pretending to be rate limits',async()=>{
  let calls=0;const git=new GitHub('owner/repo','test-only','main',async()=>{calls++;return response(403);});
  await assert.rejects(()=>git.runs(),/权限不足/);await assert.rejects(()=>git.runs(),/重新连接/);assert.equal(calls,1);
});
test('rate reset and Retry-After prevent requests during the waiting period',async()=>{
  let calls=0;const reset=Math.floor(Date.now()/1000)+120;
  const git=new GitHub('owner/repo','test-only','main',async()=>{calls++;return response(429,{'retry-after':'30','x-ratelimit-remaining':'0','x-ratelimit-reset':String(reset)});});
  await assert.rejects(()=>git.runs(),e=>e.status===429);assert.ok(git.retryAt>=reset*1000);assert.equal(git.token,'test-only');
  await assert.rejects(()=>git.dispatch({schema_version:1},'request-id'),/不会自动重提交/);assert.equal(calls,1);
});
test('secondary limit without headers waits a minute and backs off on repeated limits',async()=>{
  const git=new GitHub('owner/repo','test-only','main',async()=>response(403,{},'You have exceeded a secondary rate limit.'));
  await assert.rejects(()=>git.runs(),e=>e.status===403);assert.ok(git.pollDelay>=60000);
  git.retryAt=0;await assert.rejects(()=>git.runs());assert.ok(git.pollDelay>=120000);
});
test('an exhausted successful response is returned once, then further reads pause',async()=>{
  let calls=0;const git=new GitHub('owner/repo','test-only','main',async()=>{calls++;return response(200,{'x-ratelimit-remaining':'0','x-ratelimit-reset':String(Math.floor(Date.now()/1000)+120)});});
  await git.runs();assert.equal(git.canQuery,false);await assert.rejects(()=>git.runs());assert.equal(calls,1);
});
