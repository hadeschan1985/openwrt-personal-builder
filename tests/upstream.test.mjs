import test from 'node:test';
import assert from 'node:assert/strict';
import {mergeApproved} from '../site/lib/upstream.js';
import {defaultConfig,validate} from '../site/lib/model.js';
import {GitHub} from '../site/lib/github.js';

function fixture(){
  const catalog={versions:['25.12.6'],devices:[],default_version:'25.12.6'};
  const approved={schema_version:1,run_id:'123',approved_at:'2026-10-26T00:00:00Z',fingerprint:'a'.repeat(64),
    sources:['official','kwrt'].map(source=>({source,version:source==='official'?'25.12.7':'kwrt-25.12-20261026-12345678',label:source+' approved',builder_sha256:'b'.repeat(64),
      metadata:{profiles:{target:'x86/64',arch_packages:'x86_64',profiles:{generic:{titles:[{vendor:'Generic',model:'x86/64'}]}}},packages:Array.from({length:110},(_,i)=>`package-${i}`),package_metadata_errors:[]},
      tested_modes:['bios','uefi',source==='kwrt'?'native-vmdk-bios':'vmdk-bios']}))};
  return {catalog,approved};
}

test('approved versions merge additively without switching default or mutating catalog',()=>{
  const {catalog,approved}=fixture(),before=structuredClone(catalog);
  const result=mergeApproved(catalog,approved);
  assert.deepEqual(catalog,before);assert.equal(result.catalog.default_version,'25.12.6');
  assert.ok(result.catalog.versions.includes('25.12.7'));assert.equal(result.targets.size,2);
  assert.equal(mergeApproved(result.catalog,approved).catalog.devices.length,2);
});
test('new Kwrt versions require explicit approved catalog membership',()=>{
  const c=defaultConfig('kwrt-25.12-20261026-12345678');
  assert.notDeepEqual(validate(c),[]);
  assert.deepEqual(validate(c,null,[c.version]),[]);
  c.version='kwrt-latest';assert.notDeepEqual(validate(c,null,[c.version]),[]);
});
test('incomplete, failed, wrong-target and foreign-host metadata is rejected atomically',()=>{
  const {catalog}=fixture();
  for(const mutate of [a=>a.sources[1].tested_modes.pop(),a=>a.sources[0].metadata.profiles.target='arm/64',
    a=>a.sources[0].metadata.image_base='https://example.com/',a=>a.sources[0].metadata.package_metadata_errors=['offline'],
    a=>a.sources[0].version='SNAPSHOT',a=>a.sources.push(a.sources[0])]){
    const {approved}=fixture();mutate(approved);assert.throws(()=>mergeApproved(catalog,approved),/保留现有版本/);
  }
  assert.deepEqual(catalog.versions,['25.12.6']);
});
test('approved metadata decoding uses only same-repo API, including large blob fallback',async()=>{
  const {approved}=fixture(),calls=[];
  const encoded=Buffer.from(JSON.stringify(approved)).toString('base64');
  const git=new GitHub('owner/builds','ram-only','main',async(url,options)=>{
    calls.push({url,options});return {ok:true,status:200,json:async()=>calls.length===1?{size:1200000,encoding:'none',sha:'a'.repeat(40),download_url:'https://example.com/steal'}:{encoding:'base64',content:encoded}};
  });
  assert.deepEqual(await git.approvedUpstream(),approved);
  assert.equal(calls.length,2);assert.ok(calls.every(c=>c.url.startsWith('https://api.github.com/repos/owner/builds/')));
  assert.ok(!JSON.stringify(calls.map(c=>c.url)).includes('ram-only'));
});
test('oversize metadata and missing approval are safe failures, not untested upgrades',async()=>{
  const api=(payload,status=200)=>new GitHub('owner/repo','temporary','main',async()=>({ok:status===200,status,json:async()=>payload}));
  await assert.rejects(()=>api({size:5*1024*1024}).approvedUpstream(),/大小无效/);
  await assert.rejects(()=>api({},404).approvedUpstream(),e=>e.status===404);
});
