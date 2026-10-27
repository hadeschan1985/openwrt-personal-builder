export function boxProfile(c){return c?.builder==='kwrt'&&c.target==='armsr/armv8'&&c.profile==='box';}
export function boxErrors(c,catalog=null){
  if(c.box===undefined)return [];
  const box=c.box;
  if(!boxProfile(c)||!box||typeof box!=='object'||Array.isArray(box)||Object.keys(box).sort().join(',')!=='kernel,model'||!/^[-a-z0-9]{1,81}$/.test(box.model||'')||!/^stable-\d+\.\d+\.\d+$/.test(box.kernel||''))return ['盒子定制需要固定型号和内核，不能输入任意 DTB 或下载地址。'];
  const errors=[];
  if(!c.output.rootfs||(c.output.image_types||[]).length)errors.push('盒子镜像需要 ROOTFS 作为打包输入。');
  if(['usb_net','usb_wireless','wwan'].some(k=>c.features[k])||c.packages.some(p=>p.startsWith('kmod-')||p.startsWith('kernel')))errors.push('盒子驱动由所选内核提供，不能混装原生 OpenWrt 内核驱动。');
  if(catalog){const model=catalog.models.find(m=>m.id===box.model);if(!model?.kernels.includes(box.kernel))errors.push('此型号与内核尚无匹配且经过校验的 DTB。');}
  return errors;
}
