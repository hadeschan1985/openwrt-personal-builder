export const SOFTWARE_PROFILES=[
  {id:'network',source:'official',name:'家用网络工具',packages:['luci-app-ddns','luci-app-upnp','luci-proto-wireguard','luci-app-sqm','luci-app-statistics','luci-app-ttyd'],note:'DDNS、UPnP、WireGuard、SQM、统计与终端。安装后仍需按需求配置服务。'},
  {id:'storage',source:'official',name:'文件与下载',packages:['luci-app-samba4','luci-app-minidlna','luci-app-transmission','luci-app-aria2','luci-app-hd-idle'],note:'文件共享、媒体服务与下载管理。数据盘需另行挂载，不会自动共享目录。'},
  {id:'passwall2',source:'kwrt',name:'PassWall2 + 双核心',packages:['xray-core','sing-box','ca-bundle'],proxies:['luci-app-passwall2'],nft:true,note:'明确加入 Xray 与 sing-box，不只安装管理页面。节点由你在路由器上配置；不会自动启用代理。'},
  {id:'homeproxy',source:'kwrt',name:'HomeProxy + sing-box',packages:['sing-box','ca-bundle'],proxies:['luci-app-homeproxy'],nft:true,note:'管理页面与运行核心一并选择，需要 nftables。节点和路由规则仍需自行设置。'},
  {id:'utilities',source:'kwrt',name:'Kwrt 常用工具',packages:['luci-app-filebrowser-q','luci-app-vlmcsd','luci-app-uugamebooster','luci-app-turboacc','luci-app-natmap'],note:'文件管理、KMS、UU、加速与 NAT 映射。安装不代表已完成服务配置。'}
];
export function applySoftwareProfile(config,id,available){
  const profile=SOFTWARE_PROFILES.find(item=>item.id===id);
  if(!profile)throw new Error('找不到此软件模板。');
  if(config.builder!==profile.source)throw new Error(`请先切换到 ${profile.source==='kwrt'?'Kwrt':'OpenWrt 官方'}版本，再应用此模板。`);
  if(profile.nft&&config.firewall!=='nftables')throw new Error('此模板需要 nftables，请先调整防火墙。');
  const names=[...profile.packages,...profile.proxies||[]];
  const missing=names.filter(name=>!available.has(name));
  if(missing.length)throw new Error(`当前软件源缺少：${missing.join('、')}。未修改配置。`);
  const next=structuredClone(config);
  next.packages=[...new Set([...next.packages,...profile.packages])];
  next.proxies=[...new Set([...next.proxies,...profile.proxies||[]])];
  next.remove_packages=next.remove_packages.filter(name=>!names.includes(name));
  return next;
}
export function softwareAdvice(config){
  const chosen=new Set([...config.packages,...config.proxies]);
  const notes=[];
  if(chosen.has('luci-app-passwall2')&&!chosen.has('xray-core')&&!chosen.has('sing-box'))notes.push('PassWall2 仅选了管理页面：建议应用“双核心”模板，明确包含运行核心。');
  if(chosen.has('luci-app-openclash'))notes.push('OpenClash 的 LuCI 页面不等于已配置运行核心和节点。首次使用需在插件内检查核心；本平台不会自动下载未知二进制。');
  if(config.proxies.length>1)notes.push('同时安装多个代理不会自动解决 DNS、监听端口和透明代理冲突；实际运行建议一次只启用一个。');
  if(['luci-app-smartdns','luci-app-mosdns','luci-app-adguardhome'].filter(p=>chosen.has(p)).length>1)notes.push('多个 DNS 服务可能抢占 53 端口；安装后请安排监听端口和转发关系。');
  return notes;
}
