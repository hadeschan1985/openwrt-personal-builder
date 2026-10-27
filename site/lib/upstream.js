// Data only: never fetch or evaluate upstream JavaScript or repository scripts.
export function mergeApproved(catalog,approved){
  const invalid=()=>{throw new Error('上游更新资料未通过格式校验，保留现有版本。');};
  if(approved?.schema_version!==1||!/^\d+$/.test(approved.run_id)||!Number.isFinite(Date.parse(approved.approved_at))||
     !/^[a-f0-9]{64}$/.test(approved.fingerprint||'')||!Array.isArray(approved.sources)||approved.sources.length!==2)invalid();
  const result=structuredClone(catalog),targets=new Map(),sources=new Set();
  for(const item of approved.sources){
    const {source,version,metadata,tested_modes:modes}=item;
    if(!['official','kwrt'].includes(source)||sources.has(source))invalid();sources.add(source);
    if(!(source==='kwrt'?/^kwrt-\d{2}\.\d{2}-\d{8}(?:-[a-f0-9]{8})?$/:/^\d{2}\.\d{2}\.\d+$/).test(version||''))invalid();
    const expected=['bios','uefi',source==='kwrt'?'native-vmdk-bios':'vmdk-bios'];
    if(!Array.isArray(modes)||modes.length!==3||expected.some(mode=>!modes.includes(mode))||!/^[a-f0-9]{64}$/.test(item.builder_sha256||''))invalid();
    if(metadata?.profiles?.target!=='x86/64'||metadata.profiles.arch_packages!=='x86_64'||!metadata.profiles.profiles?.generic||
       !Array.isArray(metadata.packages)||metadata.packages.length<100||metadata.package_metadata_errors?.length||
       metadata.packages.some(p=>typeof p!=='string'||!/^[a-zA-Z0-9][a-zA-Z0-9+_.-]{0,120}$/.test(p)))invalid();
    if(metadata.image_base&&metadata.image_base!=='https://dl.openwrt.ai/releases/targets/x86/64')invalid();
    if(typeof item.label!=='string'||item.label.length>120)invalid();
    const target='x86/64',id='generic',profile=metadata.profiles.profiles[id];
    const aliases=(profile.titles||[]).map(t=>[t.vendor,t.model,t.variant].filter(Boolean).join(' '));
    const device={id,target,builder:source,version,name:aliases[0]||'Generic x86/64',aliases,metadata:`targets/${version}/${target}.json`};
    result.devices=result.devices.filter(d=>!(d.version===version&&d.target===target&&d.id===id));
    result.devices.push(device);
    if(!result.versions.includes(version))result.versions.push(version);
    result.version_labels={...result.version_labels,[version]:item.label};
    targets.set(`${version}/${target}`,structuredClone(metadata));
  }
  return {catalog:result,targets};
}
