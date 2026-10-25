export const CORE = new Set(['base-files','busybox','libc','libgcc','libgcc1','kernel','netifd','procd','uci','fstools']);
export const PACKAGE_PATTERN = /^[a-zA-Z0-9][a-zA-Z0-9+_.-]{0,120}$/;
export const PROXIES = [
  ['PassWall','passwall'],['PassWall2','passwall2'],['HomeProxy','homeproxy'],['HomeProxy Pro','homeproxy-pro'],
  ['SSR-Plus','ssr-plus'],['OpenClash','openclash'],['Nikki','nikki'],['Momo','momo'],['Meow','meow'],
  ['FullCombo Shark!','fchomo'],['Clashoo','clashoo'],['Honk','honk'],['luci-xray','xray-status'],
  ['Open-Box','open-box'],['Daed','daede'],['HiJpass','hijpass'],['v2rayA','v2raya']
].map(([name,id])=>({name,pkg:`luci-app-${id}`}));
export const THEMES = ['bootstrap','openwrt','openwrt-2020','material','argon','vantage','footstrap','shadcn','aurora','glass','liquid','noobwrt','shadcnui','fluent','rmm','luxe','alpha','spectra','kucat','openmptcprouter','routerich','teleofis','lightblue','material3'];
export const COMMON = [
  ['网络与远程','luci-app-ddns','动态 DNS'],['网络与远程','luci-app-upnp','UPnP'],['网络与远程','luci-proto-wireguard','WireGuard'],
  ['网络与远程','luci-app-zerotier','ZeroTier'],['网络与远程','luci-app-tailscale','Tailscale'],['网络与远程','luci-app-frpc','FRP 客户端'],
  ['网络与远程','luci-app-socat','端口转发'],['网络与远程','luci-app-mwan3','多 WAN'],['网络与远程','luci-app-openvpn','OpenVPN'],
  ['DNS 与过滤','luci-app-smartdns','SmartDNS'],['DNS 与过滤','luci-app-mosdns','MosDNS'],['DNS 与过滤','luci-app-adblock','广告过滤'],
  ['DNS 与过滤','luci-app-adguardhome','AdGuard Home'],['DNS 与过滤','luci-app-unblockneteasemusic','网易云音乐'],
  ['文件与 NAS','luci-app-samba4','Samba'],['文件与 NAS','luci-app-ksmbd','内核文件共享'],['文件与 NAS','luci-app-minidlna','媒体共享'],
  ['文件与 NAS','luci-app-transmission','Transmission'],['文件与 NAS','luci-app-aria2','Aria2'],['文件与 NAS','luci-app-qbittorrent','qBittorrent'],
  ['文件与 NAS','luci-app-hd-idle','硬盘休眠'],['文件与 NAS','luci-app-filebrowser-q','文件管理'],['文件与 NAS','luci-app-openlist2','OpenList'],
  ['系统与监控','luci-app-ttyd','网页终端'],['系统与监控','luci-app-statistics','系统统计'],['系统与监控','luci-app-nlbwmon','流量统计'],
  ['系统与监控','luci-app-watchcat','断网恢复'],['系统与监控','luci-app-sqm','SQM'],['系统与监控','luci-app-acme','证书申请'],
  ['系统与监控','luci-app-netdata','性能监控'],['系统与监控','luci-app-diskman','磁盘管理'],['系统与监控','luci-app-turboacc','网络加速'],
  ['系统与监控','luci-app-uugamebooster','UU 加速'],['系统与监控','luci-app-natmap','NAT 映射'],
  ['系统与监控','luci-app-vlmcsd','KMS 服务'],
  ['虚拟化','open-vm-tools','VMware Tools'],['虚拟化','qemu-ga','QEMU Guest Agent'],['虚拟化','btop','性能监控'],
].map(([group,pkg,name])=>({group,pkg,name}));

export function defaultConfig(version='25.12.6',target='x86/64',profile='generic') {
  return {schema_version:1,builder:version.startsWith('kwrt-')?'kwrt':'official',version,target,profile,packages:[],remove_packages:[],themes:['luci-theme-bootstrap'],proxies:[],firewall:'nftables',
    system:{hostname:'OpenWrt',ip:'192.168.1.1',webserver:'uhttpd',https:true,ipv6:true,signature:'',default_theme:'bootstrap',theme_mode:'auto',password_secret:false},
    network:{mode:'router',gateway:'',dhcp:true,wan_port:'',lan_ports:'',wifi_ssid:'',pppoe_secret:false,wifi_password_secret:false},
    features:{docker:false,usb_net:false,usb_wireless:false,wwan:false,istoreos:false,routerdog:false,remove_links:false},
    output:{filesystem:'squashfs',rootfs_size_mb:256,efi:true,legacy:true,vmdk:false,rootfs:false},defaults:'',overlay:''};
}
export function tokenize(value) { return [...new Set(value.trim().split(/\s+/).filter(Boolean))]; }
export function privateContent(c) { return Boolean(c.overlay||c.defaults||c.system.password_secret||c.network.pppoe_secret||c.network.wifi_password_secret); }
export function validate(c,available=null) {
  const errors=[];
  if(c?.schema_version!==1) return ['配置版本不受支持。'];
  if(!['official','kwrt'].includes(c.builder)) errors.push('构建环境无效。');
  if(c.builder==='kwrt'?(c.version!=='kwrt-25.12-20261012'||c.target!=='x86/64'):!/^\d{2}\.\d{2}\.\d+(?:-rc\d+)?$/.test(c.version||'')) errors.push('请选择已校验的固定构建版本。');
  if(!/^[a-z0-9_-]+\/[a-z0-9_-]+$/.test(c.target||'')||!/^[A-Za-z0-9_,.+-]+$/.test(c.profile||'')) errors.push('请选择有效设备。');
  for(const key of ['packages','remove_packages','themes','proxies']) {
    if(!Array.isArray(c[key])||c[key].length>512||c[key].some(x=>typeof x!=='string'||!PACKAGE_PATTERN.test(x))) errors.push(`${key} 中有非法包名或数量超过限制。`);
  }
  for(const key of ['system','network','features','output'])if(!c[key]||typeof c[key]!=='object'||Array.isArray(c[key]))errors.push(`${key} 设置格式不正确。`);
  if(errors.length) return errors;
  if(c.remove_packages.some(x=>CORE.has(x))) errors.push('不能移除必要的基础系统包。');
  if(c.builder==='kwrt'&&c.remove_packages.includes('my-default-settings'))errors.push('Kwrt 初始化依赖 my-default-settings，不能移除。');
  const selected=[...c.packages,...c.themes,...c.proxies];
  if(selected.some(x=>c.remove_packages.includes(x))) errors.push('同一个包不能同时添加和移除（包括主题和代理插件）。');
  if(!/^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,61}[A-Za-z0-9])?$/.test(c.system?.hostname||'')) errors.push('主机名格式不正确。');
  if(!ipv4(c.system?.ip,true)) errors.push('后台 IPv4 地址格式不正确。');
  if(!['router','side'].includes(c.network?.mode)) errors.push('网络模式无效。');
  if(c.network.gateway&&!ipv4(c.network.gateway)) errors.push('网关 IPv4 地址格式不正确。');
  if(c.network.mode==='side'&&!ipv4(c.network.gateway)) errors.push('旁路由需要有效的主路由网关。');
  if(ipv4(c.system.ip,true)&&ipv4(c.network.gateway)) {
    const [ip,prefix='24']=c.system.ip.split('/'), mask=Number(prefix)===0?0:(0xffffffff<<(32-Number(prefix)))>>>0;
    const integer=value=>value.split('.').reduce((n,part)=>(n*256+Number(part))>>>0,0);
    if(integer(ip)===integer(c.network.gateway)) errors.push('网关不能等于后台 IP。');
    if(c.network.mode==='side'&&((integer(ip)&mask)!==(integer(c.network.gateway)&mask)))errors.push('旁路由网关必须与后台 IP 在同一子网。');
  }
  const wan=c.network.wan_port,lan=c.network.lan_ports;
  if(typeof wan!=='string'||(wan&&!/^eth\d+$/.test(wan)))errors.push('WAN 网口格式应为 eth0 等。');
  if(typeof lan!=='string'||(lan&&!/^eth\d+(?: eth\d+)*$/.test(lan)))errors.push('LAN 网口格式应为 eth1 eth2 等。');
  if(wan&&typeof lan==='string'&&lan.split(' ').includes(wan)) errors.push('WAN 和 LAN 网口不能重复。');
  if(!c.target.startsWith('x86/')&&(wan||lan))errors.push('自定义网口映射目前仅支持 x86。');
  if(!['uhttpd','nginx','lighttpd'].includes(c.system.webserver))errors.push('Web 服务器选项无效。');
  if(c.builder!=='kwrt'&&c.system.webserver==='lighttpd')errors.push('Lighttpd 后台集成需要 Kwrt 版本。');
  if(!['nftables','iptables'].includes(c.firewall))errors.push('防火墙选项无效。');
  const themePackage=c.system.default_theme?.replace(/^(argon|bootstrap)-(light|dark)$/,'$1');
  if(!c.themes.includes(`luci-theme-${themePackage}`)) errors.push('默认主题必须已选中安装。');
  const landing=c.system.theme_mode??'auto';
  if(!['auto','overview','dashboard','istoreos','nas','next-nas','router','routerdog'].includes(landing))errors.push('默认主页模式无效。');
  if(c.builder!=='kwrt'&&(landing!=='auto'||c.features.istoreos||c.features.routerdog))errors.push('iStoreX、路由狗和自定义主页需要 Kwrt。');
  if(['istoreos','nas','next-nas','router'].includes(landing)&&!c.features.istoreos)errors.push('此主页模式需要开启 iStoreOS 风格界面。');
  if(landing==='routerdog'&&!c.features.routerdog)errors.push('此主页模式需要开启路由狗。');
  if(c.firewall==='iptables'&&selected.some(p=>['luci-app-homeproxy','luci-app-homeproxy-pro','luci-app-nikki','luci-app-xray-status','luci-app-fchomo'].includes(p))) errors.push('选中的代理插件需要 nftables。');
  if(!Number.isInteger(c.output?.rootfs_size_mb)||c.output.rootfs_size_mb<64||c.output.rootfs_size_mb>6144) errors.push('分区大小须为 64–6144 MB 的整数。');
  if(!c.target.startsWith('x86/')&&c.output.rootfs_size_mb!==256)errors.push('自定义根分区大小目前仅支持 x86。');
  if(c.output.vmdk&&!c.target.startsWith('x86/'))errors.push('VMDK 目前仅支持 x86。');
  if(c.output.vmdk&&!c.output.efi&&!c.output.legacy)errors.push('VMDK 需要 EFI 或 Legacy 磁盘映像。');
  if(c.target.startsWith('x86/')&&!c.output.efi&&!c.output.legacy&&!c.output.rootfs) errors.push('至少选择一种输出。');
  if(!['squashfs','ext4'].includes(c.output.filesystem)) errors.push('文件系统无效。');
  if(new TextEncoder().encode(c.defaults||'').length>20000) errors.push('初始化脚本不能超过 20 KB。');
  if(c.overlay&&!/^overlays\/[A-Za-z0-9_.-]+\.(zip|tar\.gz|tgz|7z)$/.test(c.overlay)) errors.push('文件包须位于 overlays/，使用 ZIP/TAR.GZ/TGZ/7Z。');
  if(c.network.mode==='side'&&c.network.pppoe_secret) errors.push('旁路由模式不使用 PPPoE。');
  if(typeof c.network.wifi_ssid!=='string'||new TextEncoder().encode(c.network.wifi_ssid).length>32||/[\x00\n]/.test(c.network.wifi_ssid))errors.push('Wi-Fi 名称不能超过 32 字节或包含换行。');
  if(c.network.wifi_password_secret&&!c.network.wifi_ssid)errors.push('设置 Wi-Fi 密码时需要填写 Wi-Fi 名称。');
  if(c.network.wifi_ssid&&!c.network.wifi_password_secret)errors.push('设置 Wi-Fi 名称时须启用 WIFI_PASSWORD，避免开放热点。');
  if(available) {
    const missing=[...c.packages,...c.themes,...c.proxies].filter(p=>!available.has(p));
    if(missing.length) errors.push(`当前软件源找不到：${missing.slice(0,8).join('、')}${missing.length>8?' 等':''}。`);
  }
  return errors;
}
export function ipv4(value,cidr=false) {
  if(typeof value!=='string')return false;
  const [ip,prefix,...rest]=value.split('/');
  return !rest.length&&/^(\d{1,3}\.){3}\d{1,3}$/.test(ip)&&ip.split('.').every(n=>Number(n)<=255)&&
    ip.split('.').every(n=>n==='0'||!n.startsWith('0'))&&
    (prefix===undefined||(cidr&&/^\d{1,2}$/.test(prefix)&&Number(prefix)<=32));
}
export function safePreset(c) {
  // Explicit projection prevents imported objects from smuggling credentials.
  const base=defaultConfig(c.version,c.target,c.profile);
  base.builder=c.builder??base.builder;
  for(const key of ['packages','remove_packages','themes','proxies','firewall','defaults','overlay']) base[key]=structuredClone(c[key]??base[key]);
  for(const key of ['system','network','features','output']) {
    for(const field of Object.keys(base[key])) if(c[key]?.[field]!==undefined) base[key][field]=c[key][field];
  }
  return base;
}
