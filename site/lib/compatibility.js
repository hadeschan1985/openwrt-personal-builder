// Explicit, evidence-bound correction of one upstream package-name defect.
const SHA=/^[a-f0-9]{64}$/;
const COMPONENTS=['kmod-hwmon-drivetemp','kmod-hwmon-emc2305','kmod-hwmon-lm75','luci-app-fan'];
export function r3dCorrection(config,release,metadata,proof){
  if(config?.builder!=='kwrt'||config.target!=='ipq806x/generic'||config.profile!=='xiaomi_r3d'||config.version!==release?.version)return null;
  const image=proof?.image_validation;
  if(proof?.schema_version!==1||proof.status!=='passed'||proof.target!==config.target||proof.profile!==config.profile||proof.hardware_tested!==false||!/^\d+$/.test(String(proof.run_id||''))||!/^[a-f0-9]{40}$/.test(proof.source_commit||'')||!SHA.test(proof.config_sha256||'')||!SHA.test(proof.policy_sha256||'')||proof.policy_sha256!==release.policy_sha256||!SHA.test(proof.target_fingerprint||'')||proof.target_fingerprint!==release.targets?.[config.target]?.target_fingerprint||proof.removed_alias!=='hwmon-drivetemp'||proof.retained_driver!=='kmod-hwmon-drivetemp'||!Array.isArray(proof.retained_components)||COMPONENTS.some(p=>!proof.retained_components.includes(p)))return null;
  if(image?.status!=='passed'||image.target!==config.target||image.profile!==config.profile||image.boot_tested!==false||image.hardware_tested!==false||!Array.isArray(image.files)||!image.files.length||image.files.some(f=>!f||typeof f!=='object'||!SHA.test(f.sha256||'')||!Number.isSafeInteger(f.bytes)||f.bytes<1))return null;
  const defaults=metadata?.profiles?.profiles?.[config.profile]?.device_packages;
  const available=new Set(metadata?.packages||[]);
  if(!defaults?.includes('hwmon-drivetemp')||available.has('hwmon-drivetemp')||COMPONENTS.some(p=>!available.has(p)))return null;
  return {proof,applied:config.remove_packages?.includes('hwmon-drivetemp')&&config.packages?.includes('kmod-hwmon-drivetemp')&&!config.remove_packages.includes('kmod-hwmon-drivetemp')&&!config.packages.includes('hwmon-drivetemp')};
}
export function applyR3dCorrection(config,release,metadata,proof){
  if(!r3dCorrection(config,release,metadata,proof))throw new Error('此修正与当前设备或验证版本不匹配。');
  const result=structuredClone(config);
  result.packages=[...new Set(result.packages.filter(p=>p!=='hwmon-drivetemp').concat('kmod-hwmon-drivetemp'))];
  result.remove_packages=[...new Set(result.remove_packages.filter(p=>p!=='kmod-hwmon-drivetemp').concat('hwmon-drivetemp'))];
  return result;
}
