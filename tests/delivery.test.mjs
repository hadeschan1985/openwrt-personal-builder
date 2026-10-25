import test from 'node:test';
import assert from 'node:assert/strict';
import {defaultConfig,safePreset,validate} from '../site/lib/model.js';
import {GitHub} from '../site/lib/github.js';
import {buildRecord,firmwareArtifact,internalRun,privateArchives,deliveryLabel} from '../site/lib/delivery.js';
const run={id:123,run_number:8,head_sha:'a'.repeat(40)};
function record(){return {schema_version:1,run_id:'123',run_number:'8',source_commit:run.head_sha,config:defaultConfig(),vm:{status:'passed'},files:[{name:'test-combined.img.gz',bytes:10,sha256:'b'.repeat(64),group:'legacy'}]};}
test('new x86 defaults enforce release gates; old presets remain explicit experiments',()=>{
  const c=defaultConfig();assert.equal(c.build_mode,'release');assert.equal(c.system.password_secret,true);
  c.system.password_secret=false;assert.ok(validate(c).some(s=>s.includes('密码')));
  delete c.build_mode;assert.equal(safePreset(c).build_mode,'experiment');
});
test('manifest identity and per-file integrity are bounded',()=>{
  assert.equal(buildRecord(record(),run).config.build_mode,'release');
  for(const mutate of [r=>r.source_commit='f'.repeat(40),r=>r.run_id='456',r=>r.files=[],r=>r.files.push(r.files[0]),r=>r.files[0].name='../secret',r=>r.files[0].bytes=2**40,r=>r.vm.status='failed']){
    const r=record();mutate(r);assert.throws(()=>buildRecord(r,run));
  }
  assert.match(deliveryLabel(null),/未通过/);
});
test('new format artifacts and legacy downloads are distinct from reports',()=>{
  for(const name of ['firmware-5','firmware-6-efi','firmware-6-vmdk','firmware-6-rootfs'])assert.equal(firmwareArtifact({name}),true);
  for(const name of ['firmware-6-reports','build-record-123','failed-build-log-6'])assert.equal(firmwareArtifact({name}),false);
  assert.equal(internalRun({display_title:'Personal firmware · qa-internal-20261026-test'}),true);
  assert.equal(internalRun({display_title:'Personal firmware · user-request'}),false);
});
test('history is paginated and latest success queried independently',async()=>{
  const paths=[],git=new GitHub('owner/repo','ram','main',async(url)=>{paths.push(url);return {ok:true,status:200,json:async()=>({size:2,encoding:'base64',content:'e30='})};});
  await git.runs(2);await git.latestSuccess();await git.buildRecord(123);
  assert.ok(paths[0].endsWith('per_page=12&page=2'));assert.ok(paths[1].includes('status=success'));assert.ok(paths[2].includes('/records/123.json'));
  assert.throws(()=>git.runs(0));assert.throws(()=>git.buildRecord('../x'));
});
test('private archive rejects other downloads, drafts and unowned tags',()=>{
  const repo='owner/repo',prefix=`https://github.com/${repo}/releases/download/personal-build-8-123/`;
  const good={id:1,tag_name:'personal-build-8-123',draft:false,assets:[{name:'disk.img.gz',browser_download_url:prefix+'disk.img.gz',size:10},{name:'bad',browser_download_url:'https://evil.test'}]};
  const result=privateArchives([good,{...good,draft:true},{...good,tag_name:'other'}],repo);
  assert.equal(result.length,1);assert.equal(result[0].assets.length,1);assert.equal(result[0].runId,'123');
});
test('archive dispatch uses only private repository and existing Actions scope',async()=>{
  let request;const git=new GitHub('owner/repo','ram','main',async(url,options)=>{request={url,...options};return {ok:true,status:204};});
  await assert.rejects(()=>git.archive(123));git.private=true;await git.archive(123);
  assert.ok(request.url.endsWith('/actions/workflows/archive.yml/dispatches'));assert.deepEqual(JSON.parse(request.body).inputs,{run_id:'123'});
});
