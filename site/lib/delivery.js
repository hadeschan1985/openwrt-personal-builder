import {safePreset,validate} from './model.js?v=20261026-7';
export function internalRun(run){return / · qa-internal-[A-Za-z0-9-]+$/.test(run?.display_title||'');}
export function firmwareArtifact(artifact){return /^firmware-\d+(?:-(efi|legacy|vmdk|rootfs))?$/.test(artifact.name||'');}
export function deliveryLabel(record){
  return record?.config?.build_mode==='release'&&record?.vm?.status==='passed'?'本次映像已通过虚拟机验收 · 未做实体硬件验证':'实验 / 旧版构建 · 未通过本流程启动验收';
}
export function buildRecord(value,run){
  if(value?.schema_version!==1||String(value.run_id)!==String(run.id)||String(value.run_number)!==String(run.run_number)||value.source_commit!==run.head_sha||
    !Array.isArray(value.files)||!value.files.length||value.files.length>100||new Set(value.files.map(f=>f.name)).size!==value.files.length||value.files.reduce((sum,f)=>sum+f.bytes,0)>1536*1024*1024||value.files.some(f=>!/^[A-Za-z0-9_.+-]{1,180}$/.test(f.name||'')||!Number.isSafeInteger(f.bytes)||f.bytes<0||!/^[a-f0-9]{64}$/.test(f.sha256||'')||!['efi','legacy','vmdk','rootfs','reports'].includes(f.group)))throw new Error('构建清单身份或格式不一致，未加载配置。');
  const config=safePreset(value.config);if(validate(config,null,[config.version]).length)throw new Error('保存的配置未通过格式校验。');
  if(config.build_mode==='release'&&value.vm?.status!=='passed')throw new Error('正式固件缺少本次映像验收结果。');
  return {...value,config};
}
export function privateArchives(releases,repo){
  return releases.filter(r=>!r.draft&&/^personal-build-\d+-\d+$/.test(r.tag_name||'')).map(r=>{
    const match=r.tag_name.match(/^personal-build-(\d+)-(\d+)$/),prefix=`https://github.com/${repo}/releases/download/${r.tag_name}/`;
    return {id:r.id,runNumber:Number(match[1]),runId:match[2],name:r.name||`收藏 #${match[1]}`,date:r.published_at,
      status:(r.body||'').includes('已通过本次映像虚拟机验收')?'本次映像已通过虚拟机验收 · 实体硬件未测':'实验 / 旧版 · 未通过本流程启动验收，请勿直接刷机',
      url:`https://github.com/${repo}/releases/tag/${r.tag_name}`,assets:(r.assets||[]).filter(a=>typeof a.browser_download_url==='string'&&a.browser_download_url.startsWith(prefix)&&/^[A-Za-z0-9_.+-]{1,180}$/.test(a.name||'')).map(a=>({name:a.name,size:a.size,url:a.browser_download_url,digest:/^sha256:[a-f0-9]{64}$/.test(a.digest||'')?a.digest.slice(7):null}))};
  });
}
