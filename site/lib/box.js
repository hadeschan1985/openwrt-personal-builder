export function boxProfile(c){return c?.builder==='kwrt'&&c.target==='armsr/armv8'&&c.profile==='box';}
export async function validateBoxCatalog(value){
  const fail=()=>{throw new Error('盒子资源与验收记录不一致，保留当前版本。');},sha=/^[a-f0-9]{64}$/;
  if(value?.schema_version!==1||!/^box-\d{8}-[a-f0-9]{8}$/.test(value.release||'')||!sha.test(value.fingerprint||'')||!sha.test(value.policy_sha256||'')||!/^\d+$/.test(String(value.run_id||''))||!/^[a-f0-9]{40}$/.test(value.source_commit||'')||!value.release.endsWith('-'+value.fingerprint.slice(0,8))||value.status!=='representative-repack-verified'||value.verification_level!=='repack-and-integrity-only'||value.hardware_tested!==false||!Array.isArray(value.models)||!value.models.length||value.models.length>2000||!Array.isArray(value.kernels)||!value.kernels.length||value.kernels.length>12||!Array.isArray(value.proofs)||!value.proofs.length||value.proofs.length>36)fail();
  const keys=['schema_version','repositories','model_database_blob','remake_blob','kernels','models','excluded_models','policy_sha256'];
  const canonical=v=>Array.isArray(v)?'['+v.map(canonical).join(',')+']':v!==null&&typeof v==='object'?'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}':JSON.stringify(v);
  const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(canonical(Object.fromEntries(keys.map(k=>[k,value[k]]))))))].map(n=>n.toString(16).padStart(2,'0')).join('');if(hash!==value.fingerprint)fail();
  const required=new Set(),seen=new Set();
  for(const model of value.models){if(!/^[-a-z0-9]{1,81}$/.test(model.id||'')||!['amlogic','rockchip','allwinner'].includes(model.platform)||!Array.isArray(model.kernels)||!model.kernels.length)fail();for(const id of model.kernels){const k=value.kernels.find(k=>k.id===id);if(!k||!sha.test(k.sha256||'')||!sha.test(k.dtbs?.[model.dtb]?.sha256||''))fail();required.add(id+'/'+model.platform);}}
  for(const proof of value.proofs){const k=value.kernels.find(k=>k.id===proof.case?.kernel),m=value.models.find(m=>m.id===proof.case?.model),r=proof.report,key=k?.id+'/'+m?.platform;if(!k||!m||!m.kernels.includes(k.id)||seen.has(key)||String(proof.run_id)!==String(value.run_id)||proof.source_commit!==value.source_commit||r?.status!=='passed'||r.model!==m.id||r.kernel!==k.id||r.kernel_release!==k.release||r.dtb!==m.dtb||r.dtb_sha256!==k.dtbs[m.dtb]?.sha256||r.kernel_asset_sha256!==k.sha256||!Number.isSafeInteger(r.module_vermagic_checked)||r.module_vermagic_checked<20||r.boot_tested!==false||r.hardware_tested!==false||proof.policy_sha256!==value.policy_sha256||proof.release!==value.release)fail();seen.add(key);}
  if([...required].some(key=>!seen.has(key)))fail();return value;
}
export function boxErrors(c,catalog=null){
  if(c.box===undefined)return [];
  const box=c.box;
  if(!boxProfile(c)||!box||typeof box!=='object'||Array.isArray(box)||!['kernel,model','kernel,model,release'].includes(Object.keys(box).sort().join(','))||!/^[-a-z0-9]{1,81}$/.test(box.model||'')||!/^(stable|rk35xx|rk3588)-\d+\.\d+\.\d+$/.test(box.kernel||'')||box.release!==undefined&&!/^box-\d{8}-[a-f0-9]{8}$/.test(box.release))return ['盒子定制需要固定型号和内核，不能输入任意 DTB 或下载地址。'];
  const errors=[];
  if(!c.output.rootfs||(c.output.image_types||[]).length)errors.push('盒子镜像需要 ROOTFS 作为打包输入。');
  if(['usb_net','usb_wireless','wwan'].some(k=>c.features[k])||c.packages.some(p=>p.startsWith('kmod-')||p.startsWith('kernel')))errors.push('盒子驱动由所选内核提供，不能混装原生 OpenWrt 内核驱动。');
  if(catalog){const model=catalog.models.find(m=>m.id===box.model);if((box.release||null)!==(catalog.release||null)||!model?.kernels.includes(box.kernel))errors.push('此型号与内核尚无匹配且经过校验的 DTB。');}
  return errors;
}
