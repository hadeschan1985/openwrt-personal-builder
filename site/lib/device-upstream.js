// Approved data only. No upstream code, credentials or arbitrary URLs are loaded.
const VERSION=/^kwrt-25\.12-\d{8}-[a-f0-9]{8}$/;
const SHA=/^[a-f0-9]{64}$/;
const COMMIT=/^[a-f0-9]{40}$/;
const PROFILE=/^[A-Za-z0-9_,.+-]{1,180}$/;
const PACKAGE=/^[A-Za-z0-9][A-Za-z0-9+_.-]{0,120}$/;
const TARGET=/^[a-z0-9_-]+\/[a-z0-9_-]+$/;
const invalid=()=>{throw new Error('设备更新资料未通过校验，保留现有版本。');};
export function validateDeviceRelease(value){
  if(value?.schema_version!==1||!VERSION.test(value.version||'')||!SHA.test(value.fingerprint||'')||!value.version.endsWith('-'+value.fingerprint.slice(0,8))||!SHA.test(value.policy_sha256||'')||!/^\d+$/.test(String(value.run_id||''))||!COMMIT.test(value.source_commit||'')||!Number.isFinite(Date.parse(value.approved_at))||value.verification_level!=='build-and-integrity-only'||value.hardware_tested!==false||typeof value.label!=='string'||value.label.length>120)invalid();
  if(!value.targets||typeof value.targets!=='object'||Array.isArray(value.targets)||Object.keys(value.targets).length<1||Object.keys(value.targets).length>128||!Array.isArray(value.devices)||value.devices.length>10000)invalid();
  let profiles=0,passed=0;const counts=new Map(),identities=new Set();
  for(const [target,item]of Object.entries(value.targets)){
    if(!TARGET.test(target)||target==='x86/64'||!SHA.test(item.metadata_sha256||'')||!SHA.test(item.builder_sha256||'')||!SHA.test(item.target_fingerprint||'')||item.metadata_path!==`updates/device-metadata/${item.metadata_sha256}/${target}.json`||!Number.isInteger(item.profile_count)||item.profile_count<1||item.profile_count>3000)invalid();
    profiles+=item.profile_count;
    if(item.status==='blocked'){if(typeof item.reason!=='string'||!item.reason.length||item.reason.length>300)invalid();}
    else if(item.status==='passed'){
      passed++;const p=item.proof,r=p?.report;
      if(p?.status!=='passed'||p.target!==target||!PROFILE.test(p.profile||'')||p.target_fingerprint!==item.target_fingerprint||p.policy_sha256!==value.policy_sha256||!VERSION.test(p.tested_version||'')||!/^\d+$/.test(String(p.run_id||''))||!COMMIT.test(p.source_commit||'')||r?.status!=='passed'||r.target!==target||r.profile!==p.profile||r.version!==p.tested_version||r.boot_tested!==false||r.hardware_tested!==false||!Array.isArray(r.files)||r.files.length<1||r.files.length>32||r.files.some(f=>!/^[A-Za-z0-9_.+-]{1,180}$/.test(f.name||'')||!Number.isSafeInteger(f.bytes)||f.bytes<1||f.bytes>1536*1024*1024||!SHA.test(f.sha256||'')))invalid();
    }else invalid();
  }
  if(!passed||profiles!==value.devices.length)invalid();
  for(const d of value.devices){
    const t=value.targets[d.target],key=`${d.target}/${d.id}`;
    if(!t||identities.has(key)||!PROFILE.test(d.id||'')||d.version!==value.version||d.builder!=='kwrt'||d.metadata!==t.metadata_path||d.private_metadata!==true||typeof d.name!=='string'||d.name.length>500||!Array.isArray(d.aliases)||d.aliases.length>30||d.aliases.some(a=>typeof a!=='string'||a.length>500))invalid();
    identities.add(key);counts.set(d.target,(counts.get(d.target)||0)+1);
  }
  for(const [target,item]of Object.entries(value.targets)){
    if(counts.get(target)!==item.profile_count||item.status==='passed'&&!identities.has(`${target}/${item.proof.profile}`))invalid();
  }
  return value;
}
export function mergeDeviceApproved(catalog,approved){
  validateDeviceRelease(approved);const result=structuredClone(catalog);
  result.devices=result.devices.filter(d=>d.version!==approved.version).concat(structuredClone(approved.devices));
  if(!result.versions.includes(approved.version))result.versions.push(approved.version);
  result.version_labels={...result.version_labels,[approved.version]:approved.label};
  return {catalog:result,release:structuredClone(approved)};
}
export function validateDeviceMetadata(data,device,approved){
  validateDeviceRelease(approved);const expected=approved.targets[device.target],profiles=data?.profiles;
  const base='https://dl.openwrt.ai/releases/targets/'+device.target;
  if(!expected||device.version!==approved.version||profiles?.target!==device.target||profiles.version_number!=='25.12-SNAPSHOT'||data.builder_sha256!==expected.builder_sha256||!data.profiles.profiles?.[device.id]||Object.keys(data.profiles.profiles).length!==expected.profile_count||!Array.isArray(data.packages)||data.packages.length<100||data.packages.length>40000||data.packages.some(p=>typeof p!=='string'||!PACKAGE.test(p))||data.package_metadata_errors?.length||data.image_base!==base&&!(device.target==='amlogic/meson8b'&&data.image_base==='https://dl.openwrt.ai/releases/25.12/targets/amlogic/meson8b'))invalid();
  for(const d of approved.devices.filter(d=>d.target===device.target))if(!profiles.profiles[d.id])invalid();
  if(expected.status==='blocked'?data.build_blocked!==expected.reason:Boolean(data.build_blocked))invalid();
  const images=profiles.profiles[device.id].images;
  if(!Array.isArray(images)||!images.length||images.some(i=>!/^[A-Za-z0-9_.+-]{1,180}$/.test(i.name||'')||!SHA.test(i.sha256||'')))invalid();
  return data;
}
