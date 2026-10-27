import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {defaultConfig} from '../site/lib/model.js';
import {r3dCorrection,applyR3dCorrection} from '../site/lib/compatibility.js';
const proof=JSON.parse(await readFile(new URL('../site/data/r3d-correction.json',import.meta.url),'utf8'));
function fixture(){
  const config=defaultConfig();Object.assign(config,{builder:'kwrt',target:proof.target,profile:proof.profile,version:proof.image_validation.version,packages:['curl','hwmon-drivetemp'],remove_packages:['kmod-hwmon-drivetemp','wpad-basic-mbedtls'],defaults:'echo retained',overlay:'uploads/personal.tar.gz'});config.network.ip='192.168.8.3';
  return {config,release:{version:config.version,policy_sha256:proof.policy_sha256,targets:{[proof.target]:{target_fingerprint:proof.target_fingerprint}}},metadata:{profiles:{profiles:{xiaomi_r3d:{device_packages:['hwmon-drivetemp']}}},packages:proof.retained_components}};
}
test('R3D correction requires explicit application, preserves personal settings and is idempotent',()=>{
  const {config,release,metadata}=fixture(),original=structuredClone(config);assert.equal(r3dCorrection(config,release,metadata,proof).applied,false);assert.deepEqual(config,original);
  const changed=applyR3dCorrection(config,release,metadata,proof);assert.deepEqual(changed.packages,['curl','kmod-hwmon-drivetemp']);assert.deepEqual(changed.remove_packages,['wpad-basic-mbedtls','hwmon-drivetemp']);assert.deepEqual(changed.network,original.network);assert.equal(changed.defaults,original.defaults);assert.equal(changed.overlay,original.overlay);assert.deepEqual(changed.system,original.system);assert.deepEqual(config,original);assert.equal(r3dCorrection(changed,release,metadata,proof).applied,true);assert.deepEqual(applyR3dCorrection(changed,release,metadata,proof),changed);
});
test('R3D evidence from another policy, platform, image or unverified hardware claim is rejected',()=>{
  for(const mutate of [f=>f.release.policy_sha256='a'.repeat(64),f=>f.release.targets[proof.target].target_fingerprint='a'.repeat(64),f=>f.config.profile='different',f=>f.config.builder='official',f=>f.config.version+='-old',f=>f.metadata.packages=[],f=>f.metadata.profiles.profiles.xiaomi_r3d.device_packages=[],f=>f.evidence.hardware_tested=true,f=>f.evidence.image_validation.profile='other',f=>f.evidence.image_validation.files[0].sha256='invalid',f=>f.evidence.retained_components.pop()]){const f={...fixture(),evidence:structuredClone(proof)};mutate(f);assert.equal(r3dCorrection(f.config,f.release,f.metadata,f.evidence),null);assert.throws(()=>applyR3dCorrection(f.config,f.release,f.metadata,f.evidence),/不匹配/);}
});
