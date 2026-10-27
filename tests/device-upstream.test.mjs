import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {GitHub} from '../site/lib/github.js';
import {mergeDeviceApproved,validateDeviceRelease,validateDeviceMetadata} from '../site/lib/device-upstream.js';

function fixture(){
  const target='airoha/an7581',version='kwrt-25.12-20261027-aaaaaaaa';
  const metadata={builder_sha256:'b'.repeat(64),image_base:`https://dl.openwrt.ai/releases/targets/${target}`,package_metadata_errors:[],packages:Array.from({length:110},(_,i)=>`package-${i}`),profiles:{target,version_number:'25.12-SNAPSHOT',profiles:{fixture:{images:[{name:'firmware.bin',sha256:'a'.repeat(64)}]}}}};
  const bytes=Buffer.from(JSON.stringify(metadata)),sha=createHash('sha256').update(bytes).digest('hex'),path=`updates/device-metadata/${sha}/${target}.json`;
  const proof={status:'passed',target,profile:'fixture',tested_version:version,target_fingerprint:'d'.repeat(64),policy_sha256:'c'.repeat(64),run_id:'123',source_commit:'e'.repeat(40),report:{status:'passed',target,profile:'fixture',version,boot_tested:false,hardware_tested:false,files:[{name:'firmware.bin',bytes:100,sha256:'a'.repeat(64)}]}};
  const approved={schema_version:1,version,fingerprint:'a'.repeat(64),policy_sha256:'c'.repeat(64),run_id:'123',source_commit:'e'.repeat(40),approved_at:'2026-10-27T00:00:00Z',label:'Kwrt 多型号验收',verification_level:'build-and-integrity-only',hardware_tested:false,targets:{[target]:{status:'passed',proof,metadata_path:path,metadata_sha256:sha,builder_sha256:'b'.repeat(64),target_fingerprint:'d'.repeat(64),profile_count:1}},devices:[{id:'fixture',target,version,name:'云端测试设备',aliases:['中文型号'],builder:'kwrt',metadata:path,private_metadata:true}]};
  return {metadata,bytes,sha,path,approved};
}
test('device release merges atomically and retains previous models and default',()=>{
  const {approved}=fixture(),catalog={versions:['25.12.6'],devices:[{name:'old'}],default_version:'25.12.6'};
  const result=mergeDeviceApproved(catalog,approved);assert.equal(catalog.devices.length,1);assert.equal(result.catalog.default_version,'25.12.6');assert.equal(result.catalog.devices.length,2);
  assert.equal(mergeDeviceApproved(result.catalog,approved).catalog.devices.length,2);
});
test('failed, incomplete, foreign, duplicate or false hardware evidence is rejected',()=>{
  for(const mutate of [a=>a.targets['x86/64']=a.targets['airoha/an7581'],a=>a.targets['airoha/an7581'].proof.report.hardware_tested=true,a=>a.devices.push(a.devices[0]),a=>a.targets['airoha/an7581'].metadata_path='https://evil.test',a=>a.version='kwrt-latest',a=>a.targets['airoha/an7581'].proof.profile='unknown',a=>a.hardware_tested=true]){
    const {approved}=fixture();mutate(approved);assert.throws(()=>validateDeviceRelease(approved),/保留现有版本/);
  }
});
test('metadata must match exact selected platform, profile, trusted source and block status',()=>{
  const {approved,metadata}=fixture();assert.equal(validateDeviceMetadata(metadata,approved.devices[0],approved),metadata);
  for(const mutate of [d=>d.profiles.target='x86/64',d=>d.image_base='https://evil.test',d=>d.build_blocked='blocked',d=>d.packages=['bad;command'],d=>d.profiles.profiles.fixture.images[0].name='../escape']){
    const bad=structuredClone(metadata);mutate(bad);assert.throws(()=>validateDeviceMetadata(bad,approved.devices[0],approved));
  }
});
test('private metadata checks raw UTF8 SHA256 and size without following download URLs',async()=>{
  const {metadata,bytes,sha,path}=fixture(),calls=[];
  const git=new GitHub('owner/builds','ram-only','main',async url=>{calls.push(url);return {ok:true,status:200,json:async()=>({size:bytes.length,encoding:'base64',content:bytes.toString('base64'),download_url:'https://evil.test'})};});
  assert.deepEqual(await git.readJSON(path,4*1024*1024,sha),metadata);assert.equal(calls.length,1);
  await assert.rejects(()=>git.readJSON(path,4*1024*1024,'f'.repeat(64)),/SHA256/);
  await assert.rejects(()=>git.readJSON('../escape'),/路径/);assert.throws(()=>git.deviceRelease('latest'),/版本/);
});
test('disconnect discards a late metadata response',async()=>{
  const {bytes,path,sha}=fixture();let release;
  const git=new GitHub('owner/builds','ram-only','main',async()=>{await new Promise(resolve=>release=resolve);return {ok:true,status:200,json:async()=>({size:bytes.length,encoding:'base64',content:bytes.toString('base64')})};});
  const pending=git.readJSON(path,4*1024*1024,sha);git.close();release();await assert.rejects(pending,/断开/);
});
