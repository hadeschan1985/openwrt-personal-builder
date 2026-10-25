import test from 'node:test';
import assert from 'node:assert/strict';
import {runStatus,active,latestBuildResults,requestRun,artifactInfo,verifyDownload,failureHelp,stageName} from '../site/lib/progress.js';
import {SOFTWARE_PROFILES,applySoftwareProfile,softwareAdvice} from '../site/lib/software.js';
import {defaultConfig,validate} from '../site/lib/model.js';
import {GitHub} from '../site/lib/github.js';

test('statuses and stages are Chinese and unknown states do not claim success',()=>{
  assert.equal(runStatus({status:'in_progress'}),'正在构建');
  assert.equal(runStatus({status:'completed',conclusion:'success'}),'构建成功');
  assert.equal(runStatus({status:'invented'}),'正在确认状态');
  assert.equal(active({status:'queued'}),true);assert.equal(active({status:'completed',conclusion:'failure'}),false);
  assert.match(stageName('Build firmware'),/依赖/);assert.match(failureHelp({name:'Build firmware'}),/预检/);
});
test('request matching is exact, not a title substring',()=>{
  const runs=[{id:1,display_title:'Personal firmware · abc-extra'},{id:2,display_title:'Personal firmware · abc'}];
  assert.equal(requestRun(runs,'abc').id,2);assert.equal(requestRun(runs,'missing'),undefined);
});
test('homepage shows manually submitted builds without a webpage request identifier',()=>{
  const run={id:100,run_number:5,status:'completed',conclusion:'success',display_title:'Personal firmware · 5'};
  assert.equal(latestBuildResults([run]).success,run);
});
test('homepage preserves last successful result while newer build is queued or failed',()=>{
  const success={id:100,run_number:5,status:'completed',conclusion:'success'};
  for(const latest of [{id:200,run_number:6,status:'queued'},{id:200,run_number:6,status:'completed',conclusion:'failure'}]){
    assert.deepEqual(latestBuildResults([success,latest]),{latest,success});
  }
});
test('newest successful build replaces old result without mutating API response',()=>{
  const a={id:100,run_number:4,status:'completed',conclusion:'success'},b={id:200,run_number:5,status:'completed',conclusion:'success'};
  const runs=[a,b];assert.equal(latestBuildResults(runs).success,b);assert.deepEqual(runs,[a,b]);
});
test('empty and unsuccessful build histories never claim a downloadable success',()=>{
  assert.deepEqual(latestBuildResults([]),{latest:null,success:null});
  assert.equal(latestBuildResults([{id:1,status:'completed',conclusion:'failure'}]).success,null);
  assert.equal(latestBuildResults([{id:1,status:'in_progress',conclusion:null}]).success,null);
});
test('large firmware ZIP digest remains visible, and expiration prevents availability',()=>{
  const a={size_in_bytes:1024*1024*1024,expires_at:'2026-10-20T00:00:00Z',digest:`sha256:${'c'.repeat(64)}`};
  const info=artifactInfo(a,Date.parse('2026-10-26T00:00:00Z'));
  assert.equal(info.expired,true);assert.equal(info.digest,'c'.repeat(64));
});
test('expiry and ZIP digest have bounded, explicit meanings',()=>{
  const now=Date.parse('2026-10-25T00:00:00Z');
  const a={expires_at:'2026-10-27T00:00:00Z',digest:`sha256:${'f'.repeat(64)}`};
  assert.deepEqual(artifactInfo(a,now),{expired:false,days:2,digest:'f'.repeat(64)});
  assert.equal(artifactInfo({...a,expired:true},now).expired,true);
  assert.equal(artifactInfo({...a,expires_at:'2026-10-24T00:00:00Z'},now).expired,true);
  assert.equal(artifactInfo({...a,digest:'javascript:alert(1)'},now).digest,null);
});
test('local ZIP verification detects mismatch and bounds memory without reading large files',async()=>{
  const file={size:3,arrayBuffer:async()=>new TextEncoder().encode('abc').buffer};
  const expected='ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad';
  assert.equal((await verifyDownload(file,expected)).ok,true);
  assert.equal((await verifyDownload(file,'0'.repeat(64))).ok,false);
  await assert.rejects(verifyDownload({...file,size:257*1024*1024},expected),/256 MiB/);
  await assert.rejects(verifyDownload(file,'bad'),/没有可用/);
});
test('all five profiles are valid, additive, idempotent and preserve private/network fields',()=>{
  for(const profile of SOFTWARE_PROFILES){
    const c=defaultConfig(profile.source==='kwrt'?'kwrt-25.12-20261012':'25.12.6');
    c.system.ip='192.168.1.253';c.defaults='echo private';c.overlay='overlays/private.zip';c.packages=['curl'];
    const available=new Set([...profile.packages,...profile.proxies||[],'curl','luci-theme-bootstrap']);
    const next=applySoftwareProfile(c,profile.id,available);
    assert.equal(next.system.ip,c.system.ip);assert.equal(next.defaults,c.defaults);assert.equal(next.overlay,c.overlay);assert.ok(next.packages.includes('curl'));
    assert.deepEqual(validate(next,available),[]);assert.deepEqual(applySoftwareProfile(next,profile.id,available),next);assert.deepEqual(c.packages,['curl']);
  }
});
test('templates fail atomically on wrong source, missing package or wrong firewall',()=>{
  const c=defaultConfig('kwrt-25.12-20261012');
  assert.throws(()=>applySoftwareProfile(c,'network',new Set()),/切换/);
  assert.throws(()=>applySoftwareProfile(c,'passwall2',new Set()),/缺少/);
  c.firewall='iptables';assert.throws(()=>applySoftwareProfile(c,'passwall2',new Set()),/nftables/);
  assert.deepEqual(c.packages,[]);
});
test('warnings distinguish management UI from service cores and potential port conflicts',()=>{
  const c=defaultConfig('kwrt-25.12-20261012');c.proxies=['luci-app-passwall2','luci-app-openclash'];c.packages=['luci-app-smartdns','luci-app-mosdns'];
  const notes=softwareAdvice(c).join(' ');assert.match(notes,/运行核心/);assert.match(notes,/53 端口/);assert.match(notes,/只启用一个/);
});
test('API errors are actionable and cannot echo returned secret payloads',async()=>{
  const api=new GitHub('owner/repo','secret','main',async()=>({ok:false,status:401,json:async()=>({message:'secret'})}));
  await assert.rejects(()=>api.jobs(123),e=>e.message.includes('到期')&&!e.message.includes('secret'));
  assert.throws(()=>api.jobs('../bad'),/ID/);
});
