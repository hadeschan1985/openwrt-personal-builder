import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {validateBoxCatalog} from '../site/lib/box.js';

const canonical=v=>Array.isArray(v)?'['+v.map(canonical).join(',')+']':v!==null&&typeof v==='object'?'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}':JSON.stringify(v);
async function fixture(){
  const c=JSON.parse(await readFile(new URL('../configs/box-builders.json',import.meta.url),'utf8'));
  const model=c.models.find(m=>m.kernels.length>=2);c.models=[{...model,kernels:model.kernels.slice(0,2)}];c.kernels=c.kernels.filter(k=>c.models[0].kernels.includes(k.id));c.excluded_models=[];c.policy_sha256='a'.repeat(64);
  const keys=['schema_version','repositories','model_database_blob','remake_blob','kernels','models','excluded_models','policy_sha256'];
  c.fingerprint=createHash('sha256').update(canonical(Object.fromEntries(keys.map(k=>[k,c[k]])))).digest('hex');c.release='box-20261028-'+c.fingerprint.slice(0,8);Object.assign(c,{status:'representative-repack-verified',verification_level:'repack-and-integrity-only',run_id:'123',source_commit:'b'.repeat(40),hardware_tested:false});
  c.proofs=c.kernels.map(k=>({case:{model:model.id,kernel:k.id},run_id:c.run_id,source_commit:c.source_commit,release:c.release,policy_sha256:c.policy_sha256,report:{status:'passed',model:model.id,kernel:k.id,kernel_release:k.release,dtb:model.dtb,dtb_sha256:k.dtbs[model.dtb].sha256,kernel_asset_sha256:k.sha256,module_vermagic_checked:25,boot_tested:false,hardware_tested:false}}));return c;
}
test('box approval accepts complete evidence bound to immutable resource bytes',async()=>{const c=await fixture();assert.equal(await validateBoxCatalog(c),c);const changed=structuredClone(c);changed.kernels[0].sha256='f'.repeat(64);await assert.rejects(validateBoxCatalog(changed),/资源与验收记录/);});
test('missing, duplicated, foreign-run and false hardware box evidence cannot install a release',async()=>{
  for(const mutate of [c=>c.proofs.pop(),c=>c.proofs.push(structuredClone(c.proofs[0])),c=>c.proofs[0].run_id='456',c=>c.proofs[0].source_commit='c'.repeat(40),c=>c.proofs[0].report.hardware_tested=true,c=>c.proofs[0].report.module_vermagic_checked='25']){const c=await fixture();mutate(c);await assert.rejects(validateBoxCatalog(c),/资源与验收记录/);}
});
