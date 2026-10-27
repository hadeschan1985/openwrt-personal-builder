import {safePreset,validate} from './model.js?v=20261027-4';
export function internalRun(run){return / · qa-internal-[A-Za-z0-9-]+$/.test(run?.display_title||'');}
export function firmwareArtifact(artifact){return /^firmware-\d+(?:-(efi|legacy|vmdk|efi-vmdk|legacy-vmdk|rootfs|device-(?:0[1-9]|[12][0-9]|3[0-2])))?$/.test(artifact.name||'');}
export function firmwareFile(name){return /(?:\.img(?:\.gz)?|\.vmdk(?:\.zip)?|\.bin|\.trx|\.itb|\.ubi|\.chk|\.tar(?:\.gz)?)$/.test(name||'');}
export function downloadLabel(name){
  if(/^personal-box-.*\.img\.gz$/.test(name))return '盒子磁盘 · IMG.GZ / Btrfs';
  if(/-emmc_burn\.img(?:\.gz)?$/.test(name))return 'USB 烧录包 · EMMC';
  if(/-device-\d{2}$/.test(name))return '设备固件 · 文件 '+name.slice(-2);
  if(/-sysupgrade(?:[_.-]|$)/.test(name))return 'sysupgrade · 设备固件';
  if(/-factory(?:[_.-]|$)/.test(name))return 'factory · 设备固件';
  if(/efi-vmdk$|combined-efi\.vmdk/.test(name))return 'EFI VMDK · 虚拟机';
  if(/legacy-vmdk$|combined\.vmdk/.test(name))return 'Legacy VMDK · 虚拟机';
  if(/-vmdk$|\.vmdk(?:\.zip)?$/.test(name))return 'VMDK · 虚拟机';
  if(/-efi$|combined-efi\.img\.gz$/.test(name))return 'EFI · 磁盘映像';
  if(/-legacy$|combined\.img\.gz$/.test(name))return 'Legacy · 磁盘映像';
  if(/-rootfs$|rootfs\.tar\.gz$/.test(name))return 'ROOTFS · 根文件系统';
  return firmwareFile(name)?'设备固件':'下载包 / 文件';
}
export function artifactFile(artifact,record){
  const match=artifact?.name?.match(/^firmware-(\d+)-device-(0[1-9]|[12][0-9]|3[0-2])$/);
  if(!match||String(record?.run_number)!==match[1]||!Array.isArray(record.files))return null;
  return record.files.filter(f=>f.group==='device')[Number(match[2])-1]||null;
}
export function deliveryLabel(record){
  if(record?.config?.build_mode==='device'&&record?.image_validation?.status==='passed')return '本次设备固件已编译和文件校验 · 未验证开机和实体硬件';
  return record?.config?.build_mode==='release'&&record?.vm?.status==='passed'?'本次映像已通过虚拟机验收 · 未做实体硬件验证':'实验 / 旧版构建 · 未通过本流程启动验收';
}
export function buildRecord(value,run){
  if(value?.schema_version!==1||String(value.run_id)!==String(run.id)||String(value.run_number)!==String(run.run_number)||value.source_commit!==run.head_sha||
    !Array.isArray(value.files)||!value.files.length||value.files.length>100||new Set(value.files.map(f=>f.name)).size!==value.files.length||value.files.reduce((sum,f)=>sum+f.bytes,0)>1536*1024*1024||value.files.some(f=>!/^[A-Za-z0-9_.+-]{1,180}$/.test(f.name||'')||!Number.isSafeInteger(f.bytes)||f.bytes<0||!/^[a-f0-9]{64}$/.test(f.sha256||'')||!['efi','legacy','vmdk','rootfs','reports','device'].includes(f.group)))throw new Error('构建清单身份或格式不一致，未加载配置。');
  const config=safePreset(value.config);if(validate(config,null,[config.version]).length)throw new Error('保存的配置未通过格式校验。');
  if(config.build_mode==='release'&&value.vm?.status!=='passed')throw new Error('正式固件缺少本次映像验收结果。');
  if(config.build_mode==='device'&&(value.image_validation?.status!=='passed'||value.image_validation?.boot_tested!==false||['version','target','profile'].some(k=>value.image_validation[k]!==config[k])))throw new Error('设备固件缺少匹配的文件校验结果。');
  return {...value,config};
}
export function privateArchives(releases,repo){
  return releases.filter(r=>!r.draft&&/^personal-build-\d+-\d+$/.test(r.tag_name||'')).map(r=>{
    const match=r.tag_name.match(/^personal-build-(\d+)-(\d+)$/),prefix=`https://github.com/${repo}/releases/download/${r.tag_name}/`;
    return {id:r.id,runNumber:Number(match[1]),runId:match[2],name:r.name||`收藏 #${match[1]}`,date:r.published_at,
      status:(r.body||'').includes('已通过本次映像虚拟机验收')?'本次映像已通过虚拟机验收 · 实体硬件未测':(r.body||'').includes('已编译和文件校验')?'已编译和文件校验 · 未验证开机和实体硬件':'实验 / 旧版 · 未通过本流程启动验收，请勿直接刷机',
      url:`https://github.com/${repo}/releases/tag/${r.tag_name}`,assets:(r.assets||[]).filter(a=>typeof a.browser_download_url==='string'&&a.browser_download_url.startsWith(prefix)&&/^[A-Za-z0-9_.+-]{1,180}$/.test(a.name||'')).map(a=>({name:a.name,size:a.size,url:a.browser_download_url,digest:/^sha256:[a-f0-9]{64}$/.test(a.digest||'')?a.digest.slice(7):null}))};
  });
}
