import test from 'node:test';
import assert from 'node:assert/strict';
import {defaultConfig,validate,tokenize,safePreset,privateContent} from '../site/lib/model.js';
import {GitHub,repositoryName} from '../site/lib/github.js';

test('default config is valid; duplicate package tokens collapse',()=>{
  assert.deepEqual(validate(defaultConfig()),[]);
  assert.deepEqual(tokenize('curl  curl\nhtop'),['curl','htop']);
});
test('network timeouts advise checking history before retrying a build',async()=>{
  const git=new GitHub('owner/repo','session-only','main',async()=>{throw new DOMException('Timed out','TimeoutError');});
  await assert.rejects(()=>git.request('/actions/runs'),/先查看构建记录/);
});
test('Kwrt config preserves its builder and checks NAS feature requirements',()=>{
  const c=defaultConfig('kwrt-25.12-20261012');
  assert.equal(c.builder,'kwrt');
  assert.equal(safePreset(c).builder,'kwrt');
  c.system.theme_mode='nas';
  assert.ok(validate(c).some(e=>e.includes('iStoreOS')));
  c.features.istoreos=true;assert.deepEqual(validate(c),[]);
  c.overlay='overlays/private.7z';assert.deepEqual(validate(c),[]);
});
test('unavailable package and essential removals are surfaced',()=>{
  const c=defaultConfig();c.packages=['luci-app-not-real'];c.remove_packages=['base-files'];
  const errors=validate(c,new Set(['luci-theme-bootstrap']));
  assert.ok(errors.some(e=>e.includes('必要')));assert.ok(errors.some(e=>e.includes('luci-app-not-real')));
});
test('nft proxy conflict and invalid output are rejected',()=>{
  const c=defaultConfig();c.proxies=['luci-app-nikki'];c.firewall='iptables';c.output.efi=false;c.output.legacy=false;
  assert.ok(validate(c).some(e=>e.includes('nftables')));
  assert.ok(validate(c).some(e=>e.includes('至少选择')));
});
test('presets never project tokens or plaintext secret fields',()=>{
  const c=defaultConfig();c.token='secret-token';c.system.password='plaintext';c.github={token:'other-secret'};
  const serialized=JSON.stringify(safePreset(c));
  assert.ok(!serialized.includes('secret-token'));assert.ok(!serialized.includes('plaintext'));assert.ok(!serialized.includes('other-secret'));
});
test('sensitive overlays require a private build workflow',()=>{
  const c=defaultConfig();assert.equal(privateContent(c),false);c.overlay='overlays/personal.zip';assert.equal(privateContent(c),true);
});

test('side router must use the same subnet, including CIDR boundaries',()=>{
  const c=defaultConfig();c.network.mode='side';c.system.ip='192.168.1.129/25';c.network.gateway='192.168.1.1';
  assert.ok(validate(c).some(e=>e.includes('同一子网')));
  c.network.gateway='192.168.1.130';assert.deepEqual(validate(c),[]);
  c.system.ip='192.168.1.129/0';c.network.gateway='10.0.0.1';assert.deepEqual(validate(c),[]);
});

test('Wi-Fi cannot silently create an open hotspot',()=>{
  const c=defaultConfig();c.network.wifi_ssid='Personal';
  assert.ok(validate(c).some(e=>e.includes('避免开放热点')));
  c.network.wifi_password_secret=true;assert.deepEqual(validate(c),[]);
});

test('malformed imported settings and port mapping produce validation messages',()=>{
  const c=defaultConfig();c.network=null;assert.ok(validate(c).some(e=>e.includes('network')));
  c.network=defaultConfig().network;c.network.lan_ports='eth1; touch /tmp/pwn';
  assert.ok(validate(c).some(e=>e.includes('LAN 网口')));
  c.network.lan_ports='';c.system.ip='192.168.001.1';assert.ok(validate(c).some(e=>e.includes('IPv4')));
});
test('repository input cannot redirect credentials to another host',()=>{
  assert.throws(()=>repositoryName('https://example.com/steal'));
  assert.throws(()=>repositoryName('owner/repo/../../x'));
});
test('dispatch uses JSON API body, credentials only in authorization header',async()=>{
  const calls=[];
  const mock=async(url,options)=>{calls.push({url,options});return {ok:true,status:204};};
  const api=new GitHub('test-owner/builds','temporary-token','main',mock);
  await api.dispatch(defaultConfig(),'request-123');
  assert.equal(calls[0].url,'https://api.github.com/repos/test-owner/builds/actions/workflows/build.yml/dispatches');
  assert.equal(calls[0].options.headers.Authorization,'Bearer temporary-token');
  assert.ok(!calls[0].options.body.includes('temporary-token'));
  assert.equal(JSON.parse(calls[0].options.body).inputs.request_id,'request-123');
});

test('overlay upload normalizes uppercase extensions and stays private',async()=>{
  const calls=[];
  const mock=async(url,options)=>{calls.push({url,options});return options.method==='PUT'?{ok:true,status:201,json:async()=>({})}:{ok:false,status:404,json:async()=>({message:'Not Found'})};};
  const api=new GitHub('test-owner/builds','temporary-token','main',mock);
  const file={name:'Personal.TAR.GZ',size:4,arrayBuffer:async()=>new Uint8Array([1,2,3,4]).buffer};
  await assert.rejects(api.upload(file),/私有/);
  api.private=true;const path=await api.upload(file);
  assert.match(path,/^overlays\/[0-9a-f]{24}\.tar\.gz$/);
  assert.equal(calls.at(-1).options.method,'PUT');
  assert.ok(!calls.at(-1).options.body.includes('temporary-token'));
});
