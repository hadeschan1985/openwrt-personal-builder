import {COMMON,CORE,PROXIES,THEMES,defaultConfig,tokenize,validate,privateContent,safePreset} from './lib/model.js?v=20261025-4';
import {GitHub,repositoryName} from './lib/github.js?v=20261025-4';

const $=id=>document.getElementById(id);
const state={catalog:null,device:null,target:null,available:new Set(),config:defaultConfig(),git:null,file:null,loadId:0,loading:false,metadataReady:false,busy:false};
const targetCache=new Map();
let toastTimer;
function toast(message){$('toast').textContent=message;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,4500);}
function notice(message,kind=''){const n=$('notice');n.textContent=message;n.className='notice '+kind;}
async function json(url){const r=await fetch(url);if(!r.ok)throw new Error(`资料读取失败（${r.status}）`);return r.json();}
function node(tag,text,className){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(className)e.className=className;return e;}
const val=id=>$(id).value;
const checked=id=>$(id).checked;
function clearSelectedFile(){state.file=null;$('overlay-file').value='';$('upload-label').textContent='选择文件包';}
const bindings={
  system:{hostname:'hostname',ip:'ip',webserver:'webserver',signature:'signature',default_theme:'default-theme',theme_mode:'theme-mode'},
  network:{mode:'network-mode',gateway:'gateway',wan_port:'wan-port',lan_ports:'lan-ports',wifi_ssid:'wifi-ssid'},
  output:{filesystem:'filesystem'}
};
const checks={system:{https:'https',ipv6:'ipv6',password_secret:'password-secret'},network:{dhcp:'dhcp',pppoe_secret:'pppoe-secret',wifi_password_secret:'wifi-secret'},output:{efi:'efi',legacy:'legacy',vmdk:'vmdk',rootfs:'rootfs'}};
function readForm(){
  const c=structuredClone(state.config);
  for(const [group,fields] of Object.entries(bindings))for(const [key,id]of Object.entries(fields))c[group][key]=val(id);
  for(const [group,fields] of Object.entries(checks))for(const [key,id]of Object.entries(fields))c[group][key]=checked(id);
  c.output.rootfs_size_mb=Number(val('rootfs-size'));
  c.packages=tokenize(val('custom-packages'));c.firewall=val('firewall');c.defaults=val('defaults');c.overlay=val('overlay-path').trim();
  for(const key of ['docker','usb_net','usb_wireless','wwan','istoreos','routerdog','remove_links'])c.features[key]=checked(`feature-${key}`);
  return c;
}
function applyForm(c){
  for(const [group,fields]of Object.entries(bindings))for(const [key,id]of Object.entries(fields))$(id).value=c[group][key];
  for(const [group,fields]of Object.entries(checks))for(const [key,id]of Object.entries(fields))$(id).checked=c[group][key];
  $('rootfs-size').value=c.output.rootfs_size_mb;$('custom-packages').value=c.packages.join(' ');$('firewall').value=c.firewall;$('defaults').value=c.defaults;$('overlay-path').value=c.overlay;
  for(const key of ['docker','usb_net','usb_wireless','wwan','istoreos','routerdog','remove_links'])$(`feature-${key}`).checked=c.features[key]||false;
  conditionalFields();
}
function browserSnapshot(c){const result=safePreset(c);result.defaults='';result.overlay='';return result;}
function persist(){
  try{localStorage.setItem('pb-autofill',String(checked('autofill')));if(checked('autofill'))localStorage.setItem('pb-current',JSON.stringify(browserSnapshot(state.config)));else localStorage.removeItem('pb-current');}catch{toast('浏览器储存不可用，仍可导出配置。');}
}
function update(){
  if(!state.device)return;
  state.config=readForm();
  const c=state.config,errors=validate(c,state.available);
  $('summary-device').textContent=state.device.name;$('summary-version').textContent=c.version;
  $('summary-packages').textContent=`${new Set([...c.packages,...c.themes,...c.proxies]).size} 个`;
  $('summary-removed').textContent=`${c.remove_packages.length} 个`;
  $('summary-output').textContent=[c.output.efi?'EFI':'',c.output.legacy?'Legacy':'',c.output.vmdk?'VMDK':'',c.output.rootfs?'ROOTFS':''].filter(Boolean).join(' / ')||c.output.filesystem;
  const panel=$('validation');panel.replaceChildren();panel.classList.toggle('invalid',errors.length>0);
  if(errors.length){const list=node('ul');errors.forEach(e=>list.append(node('li',e)));panel.append(list);}else panel.textContent=privateContent(c)||state.file?'配置已通过基础检查。含私人内容，须在私有仓库构建。':'配置已通过基础检查。构建时会再次检查依赖和映像支持。';
  if(!errors.length&&!c.system.password_secret)panel.textContent+=' 尚未设置后台密码：仅建议用于实验，实际使用前请启用密码设置。';
  for(const e of document.querySelectorAll('[data-package]')){
    const group=e.dataset.group,pkg=e.dataset.package;
    e.classList.toggle('selected',c[group]?.includes(pkg));
    if(group==='remove_packages')e.classList.toggle('removed',c[group].includes(pkg));
    e.setAttribute('aria-pressed',String(c[group]?.includes(pkg)));
  }
  persist();
}
function conditionalFields(){
  const side=val('network-mode')==='side',x86=state.config.target.startsWith('x86/');
  $('gateway-field').hidden=!side;$('gateway').required=side;
  $('theme-mode').disabled=state.config.builder!=='kwrt';
  if(val('wan-port')==='eth0'&&!val('lan-ports').trim())$('lan-ports').value='eth1';
  for(const option of $('webserver').options)option.disabled=option.value==='lighttpd'&&state.config.builder!=='kwrt';
  $('pppoe-secret').disabled=side;if(side)$('pppoe-secret').checked=false;
  $('dhcp-help').textContent=side?'旁路由开启 DHCP 时，须关闭主路由 DHCP；关闭时需要终端正确指定网关和 DNS。':'主路由模式下通常开启 DHCP。';
  for(const id of ['wan-port','lan-ports','rootfs-size','efi','legacy','vmdk'])$(id).disabled=!x86;
  if(!x86){$('wan-port').value='';$('lan-ports').value='';$('rootfs-size').value=256;$('vmdk').checked=false;}
  for(const b of document.querySelectorAll('#proxy-packages button')){
    const nft=['luci-app-homeproxy','luci-app-nikki','luci-app-xray-status','luci-app-fchomo'].includes(b.dataset.package);
    const blocked=nft&&val('firewall')==='iptables';
    b.disabled=!state.available.has(b.dataset.package)||blocked;
  }
}
function chip(pkg,name,group,{disabled=false,help=''}={}){
  const button=node('button',name,'chip');button.type='button';button.dataset.package=pkg;button.dataset.group=group;button.disabled=disabled;button.title=help||pkg;button.setAttribute('aria-pressed','false');
  if(disabled)button.append(node('small',group==='remove_packages'?'必要包':'源中无此包'));
  button.addEventListener('click',()=>{
    state.config=readForm();const items=new Set(state.config[group]);items.has(pkg)?items.delete(pkg):items.add(pkg);state.config[group]=[...items];
    if(group==='packages')$('custom-packages').value=state.config.packages.join(' ');
    if(group==='themes')renderDefaultThemes();update();
  });return button;
}
function renderDefaultThemes(){
  const old=state.config.system.default_theme;const select=$('default-theme');select.replaceChildren();
  for(const pkg of state.config.themes){const theme=pkg.replace('luci-theme-','');select.add(new Option(theme,theme));if(['argon','bootstrap'].includes(theme)){select.add(new Option(`${theme} · 浅色`,`${theme}-light`));select.add(new Option(`${theme} · 深色`,`${theme}-dark`));}}
  select.value=old;if(!select.value&&select.options.length){select.selectedIndex=0;state.config.system.default_theme=select.value;}
}
function renderPackages(){
  const meta=state.target.profiles,profile=meta.profiles[state.device.id];
  const factory=[...new Set([...(meta.default_packages||[]),...(profile.device_packages||[])])].sort();
  $('factory-count').textContent=`${factory.length} 个`;$('factory-packages').replaceChildren(...factory.map(pkg=>chip(pkg,pkg,'remove_packages',{disabled:CORE.has(pkg)||(state.config.builder==='kwrt'&&pkg==='my-default-settings')})));
  $('package-count').textContent=`${state.available.size.toLocaleString()} 个可用包`;
  const groups=new Map();for(const item of COMMON){if(!groups.has(item.group))groups.set(item.group,[]);groups.get(item.group).push(item);}
  $('common-packages').replaceChildren();
  for(const [title,items]of groups){const wrap=node('div',undefined,'package-group');wrap.append(node('p',title));const chips=node('div',undefined,'chips');for(const item of items)chips.append(chip(item.pkg,item.name,'packages',{disabled:!state.available.has(item.pkg)}));wrap.append(chips);$('common-packages').append(wrap);}
  $('proxy-packages').replaceChildren(...PROXIES.map(item=>chip(item.pkg,item.name,'proxies',{disabled:!state.available.has(item.pkg)})));
  $('theme-packages').replaceChildren(...THEMES.map(theme=>chip(`luci-theme-${theme}`,theme,'themes',{disabled:!state.available.has(`luci-theme-${theme}`)})));
  renderDefaultThemes();
  const optional={docker:['luci-app-dockerman'],usb_net:['kmod-usb-net-rtl8152','kmod-usb-net-asix','kmod-usb-net-cdc-ether','kmod-usb-net-cdc-ncm'],usb_wireless:['kmod-mt76-usb','kmod-rt2800-usb','iw','wpad-mbedtls'],wwan:['luci-proto-modemmanager','modemmanager','kmod-usb-net-qmi-wwan','kmod-usb-serial-option'],istoreos:['luci-app-istorex'],routerdog:['luci-app-routerdog']};
  if(state.config.builder==='kwrt')optional.wwan=['luci-app-wwand','luci-proto-wwand','wwand-esim','wwand-mbim','wwand-mhi','wwand-ncm'];
  for(const [feature,pkgs]of Object.entries(optional)){
    const field=$(`feature-${feature}`);field.disabled=pkgs.some(p=>!state.available.has(p));
    field.parentElement.title=field.disabled?'当前软件源缺少一个或多个依赖包':pkgs.join(' ');
  }
}
async function targetData(device){
  const key=`${device.version}/${device.target}`;
  if(targetCache.has(key))return targetCache.get(key);
  let data;
  try{data=await json(`data/${device.metadata}`);}catch{
    if(device.builder==='kwrt')throw new Error('Kwrt 固定版本资料不可用，请稍后重试；不会混用官方软件源');
    const profiles=await json(`https://downloads.openwrt.org/releases/${device.version}/targets/${device.target}/profiles.json`);
    const branch=device.version.split('.').slice(0,2).join('.');
    const indexes=await Promise.allSettled([json(`https://sysupgrade.openwrt.org/json/v1/releases/${device.version}/targets/${device.target}/index.json`),json(`https://sysupgrade.openwrt.org/json/v1/releases/packages-${branch}/${profiles.arch_packages}-index.json`)]);
    const packages=new Set();indexes.forEach((r,i)=>{if(r.status==='fulfilled')Object.keys(i===0?r.value.packages:r.value).forEach(p=>packages.add(p));});
    data={profiles,packages:[...packages],package_metadata_errors:indexes.filter(r=>r.status==='rejected').map(()=> '部分软件包索引读取失败')};
  }
  targetCache.set(key,data);return data;
}
async function selectDevice(device,config=null){
  const requestId=++state.loadId;notice('正在读取设备详情和可用软件包…');$('device-results').hidden=true;$('device-search').setAttribute('aria-expanded','false');
  state.loading=true;state.metadataReady=false;$('build-button').disabled=true;$('preview-button').disabled=true;
  try{
    const data=await targetData(device);if(requestId!==state.loadId)return;
    state.device=device;state.target=data;state.available=new Set(data.packages);state.config=config||defaultConfig(device.version,device.target,device.id);
    clearSelectedFile();
    $('device-search').value=device.name;$('version').value=device.version;
    $('device-count').textContent=`${state.catalog.devices.filter(d=>d.version===device.version).length.toLocaleString()} 个设备档案`;
    $('device-name').textContent=device.name;$('device-platform').textContent=`${device.target} · ${device.id}`;
    $('target-label').textContent=device.target;$('arch-label').textContent=data.profiles.arch_packages;
    $('builder-label').textContent=device.builder==='kwrt'?'Kwrt ImageBuilder':'官方 ImageBuilder';
    $('kernel-label').textContent=data.profiles.linux_kernel?.version||'查看构建环境';
    const images=data.profiles.profiles[device.id]?.images||[];
    $('official-images').replaceChildren();
    const imageBase=data.image_base||`https://downloads.openwrt.org/releases/${device.version}/targets/${device.target}`;
    for(const image of images){const row=node('div',undefined,'download-item');const link=node('a',`${image.type} · ${image.filesystem} · ${(image.size/1048576).toFixed(1)} MiB ↗`);link.href=`${imageBase}/${encodeURIComponent(image.name)}`;link.target='_blank';link.rel='noreferrer';row.append(link,node('code',`SHA256 ${image.sha256}`));$('official-images').append(row);}
    renderPackages();applyForm(state.config);update();
    const source=device.builder==='kwrt'?'Kwrt 固定构建包':'OpenWrt 官方';
    notice(data.package_metadata_errors.length?'设备资料已载入，但部分包索引不可用；请刷新后再构建。':`${source}资料已载入。`+(state.git?`已连接构建仓库 ${state.git.repo}。`:'可导出配置，在 GitHub 手动构建；连接仓库授权后也可直接提交。'),data.package_metadata_errors.length?'warning':'');
    state.metadataReady=true;return true;
  }catch(error){if(requestId===state.loadId)notice(`设备资料载入失败：${error.message}。可重新选择或刷新。`,'error');return false;
  }finally{if(requestId===state.loadId){state.loading=false;$('build-button').disabled=state.busy||!state.metadataReady;$('preview-button').disabled=!state.metadataReady;}}
}
function showDevices(){
  const value=val('device-search').toLowerCase().trim(),version=val('version');
  const devices=state.catalog.devices.filter(d=>d.version===version&&[d.name,d.target,d.id,...d.aliases].some(s=>s.toLowerCase().includes(value))).sort((a,b)=>Number(b.target==='x86/64')-Number(a.target==='x86/64')).slice(0,40);
  $('device-results').replaceChildren();
  for(const d of devices){const b=node('button',d.name);b.type='button';b.setAttribute('role','option');b.append(node('small',`${d.target} · ${d.id}`));b.addEventListener('click',()=>selectDevice(d));$('device-results').append(b);}
  if(!devices.length)$('device-results').append(node('p','未找到匹配设备。','help'));
  $('device-results').hidden=false;$('device-search').setAttribute('aria-expanded','true');
}
function renderFeatures(){
  for(const [id,label]of [['docker','Docker 管理'],['usb_net','USB 有线网卡'],['usb_wireless','USB 无线网卡'],['wwan','WWAN / 蜂窝网络'],['istoreos','iStoreOS 风格界面'],['routerdog','路由狗 / NAS 模式'],['remove_links','去除作者外链']]){
    const labelNode=node('label',undefined,'check');const input=node('input');input.type='checkbox';input.id=`feature-${id}`;labelNode.append(input,document.createTextNode(label));if(id==='remove_links')labelNode.title='仅隐藏发行方推广链接，保留文字、开源许可和源码入口';$('feature-options').append(labelNode);
  }
}
function presetOptions(){
  $('preset-list').replaceChildren(new Option('选择已保存模板…',''));
  try{const presets=JSON.parse(localStorage.getItem('pb-presets')||'{}');for(const name of Object.keys(presets))$('preset-list').add(new Option(name,name));}catch{}
}
function configText(){return JSON.stringify(readForm(),null,2);}
function showConfig(){
  $('config-json').value=configText();
  try{$('manual-run').href=`https://github.com/${repositoryName(val('repository'))}/actions/workflows/build.yml`;$('manual-run').hidden=false;}catch{$('manual-run').hidden=true;}
  $('config-dialog').showModal();
}
async function refreshRuns(){
  if(!state.git){toast('先连接你的 GitHub 构建仓库。');return;}
  $('run-list').textContent='正在读取真实构建记录…';
  try{const {workflow_runs:runs}=await state.git.runs();$('run-list').replaceChildren();$('run-list').classList.toggle('empty',!runs.length);
    if(!runs.length){$('run-list').textContent='这个仓库还没有构建记录。';return;}
    for(const run of runs){const row=node('div',undefined,'run');const main=node('div');const a=node('a',run.display_title||`构建 #${run.run_number}`);a.href=run.html_url;a.target='_blank';a.rel='noreferrer';main.append(a,node('small',new Date(run.created_at).toLocaleString()));const status=node('div');status.append(node('span',run.conclusion||run.status,'pill'));const link=node('a','日志与下载 ↗');link.href=run.html_url;link.target='_blank';link.rel='noreferrer';status.append(node('br'),link);row.append(main,status);$('run-list').append(row);}
  }catch(error){$('run-list').textContent=error.message;}
}
async function connect(){
  $('connect-error').textContent='';$('confirm-connect').disabled=true;
  try{const git=new GitHub(val('repository').trim(),val('github-token').trim(),val('branch').trim());const data=await git.connect();state.git=git;$('github-token').value='';
    // Store only the repository and branch. GitHub credentials remain in RAM.
    localStorage.setItem('pb-repository',git.repo);localStorage.setItem('pb-branch',git.ref);
    $('connection-label').textContent=`${git.repo.split('/')[1]} · ${data.private?'私有':'公开'}`;
    $('connection-dot').classList.add('connected');$('connect-dialog').close();toast('仓库已连接。令牌仅保存在本页内存中。');notice(`已连接${data.private?'私有':'公开'}构建仓库 ${git.repo}。`);await refreshRuns();
    $('history-link').href=`https://github.com/${git.repo}/actions/workflows/build.yml`;
  }catch(error){$('connect-error').textContent=error.message;}finally{$('confirm-connect').disabled=false;}
}
async function startBuild(){
  if(state.loading||!state.metadataReady){toast('请等设备资料载入完成后再构建。');return;}
  state.config=readForm();const errors=validate(state.config,state.available);if(errors.length){update();toast(errors[0]);return;}
  if(!state.git?.token){showConfig();toast('可导出配置并手动运行，或连接仓库授权后直接构建。');return;}
  if((privateContent(state.config)||state.file)&&!state.git.private){toast('初始化脚本、密码引用和文件包须使用私有构建仓库。');return;}
  const config=structuredClone(state.config),file=state.file,git=state.git;
  const button=$('build-button');state.busy=true;button.disabled=true;button.textContent='正在提交…';
  try{if(file){config.overlay=await git.upload(file);if(state.file===file){state.config.overlay=config.overlay;$('overlay-path').value=config.overlay;}}
    const requestId=crypto.randomUUID();await git.dispatch(config,requestId);toast('GitHub 已接受构建请求。请刷新记录查看排队状态。');notice(`构建请求已提交：${config.version} / ${config.profile}。GitHub 执行期间可关闭页面，日志和产物在构建记录中。`);await refreshRuns();
  }catch(error){notice(error.message,'error');}finally{state.busy=false;button.disabled=!state.metadataReady;button.replaceChildren(document.createTextNode('构建新固件 '),node('span','↗'));}
}
async function restore(config){
  const clean=safePreset(config),errors=validate(clean);if(errors.length)throw new Error(errors[0]);
  const device=state.catalog.devices.find(d=>d.version===clean.version&&d.target===clean.target&&d.id===clean.profile);if(!device)throw new Error('此配置的版本/设备不在当前目录中。');
  if(!await selectDevice(device,clean))throw new Error('此设备资料未载入，配置尚未导入。');
}
async function init(){
  renderFeatures();presetOptions();
  $('repository').value=localStorage.getItem('pb-repository')||'hadeschan1985/openwrt-personal-builds';$('branch').value=localStorage.getItem('pb-branch')||'main';$('autofill').checked=localStorage.getItem('pb-autofill')!=='false';
  $('builder-form').addEventListener('submit',e=>e.preventDefault());
  $('builder-form').addEventListener('input',update);
  $('builder-form').addEventListener('change',e=>{if(e.target.id==='network-mode')$('dhcp').checked=val('network-mode')==='router';conditionalFields();update();});
  $('device-search').addEventListener('input',()=>state.catalog&&showDevices());$('device-search').addEventListener('focus',()=>state.catalog&&showDevices());
  $('device-search').addEventListener('keydown',e=>{if(e.key==='Escape'){$('device-results').hidden=true;$('device-search').setAttribute('aria-expanded','false');}if(e.key==='ArrowDown'){$('device-results').querySelector('button')?.focus();e.preventDefault();}});
  document.addEventListener('click',e=>{if(!e.target.closest('.search-field')){$('device-results').hidden=true;$('device-search').setAttribute('aria-expanded','false');}});
  $('version').addEventListener('change',()=>{const devices=state.catalog.devices.filter(d=>d.version===val('version'));$('device-count').textContent=`${devices.length.toLocaleString()} 个设备档案`;selectDevice(devices.find(d=>d.id===state.device?.id&&d.target===state.device?.target)||devices.find(d=>d.target==='x86/64')||devices[0]);});
  $('package-search').addEventListener('input',()=>{const query=val('package-search').toLowerCase().trim();$('package-results').replaceChildren();if(query)for(const pkg of [...state.available].filter(p=>p.includes(query)).slice(0,12))$('package-results').append(chip(pkg,pkg,'packages'));update();});
  $('preview-button').addEventListener('click',showConfig);$('build-button').addEventListener('click',startBuild);
  $('connect-button').addEventListener('click',()=>$('connect-dialog').showModal());$('confirm-connect').addEventListener('click',connect);
  $('refresh-runs').addEventListener('click',refreshRuns);
  $('copy-config').addEventListener('click',async()=>{try{await navigator.clipboard.writeText($('config-json').value);toast('构建配置已复制。下一步打开 GitHub。');}catch{toast('自动复制不可用，请展开配置明细后复制。');}});
  $('download-config').addEventListener('click',()=>{const url=URL.createObjectURL(new Blob([$('config-json').value],{type:'application/json'}));const a=node('a');a.href=url;a.download=`openwrt-${state.config.target.replace('/','-')}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
  $('autofill').addEventListener('change',persist);
  $('save-preset').addEventListener('click',()=>{const name=val('preset-name').trim();if(!name){toast('先给模板起一个名字。');return;}const presets=JSON.parse(localStorage.getItem('pb-presets')||'{}');presets[name]=browserSnapshot(readForm());localStorage.setItem('pb-presets',JSON.stringify(presets));presetOptions();toast('模板已保存在本机；初始化脚本和文件包路径未自动保存。');});
  $('preset-list').addEventListener('change',async()=>{if(!val('preset-list'))return;try{await restore(JSON.parse(localStorage.getItem('pb-presets'))[val('preset-list')]);toast('模板已载入。');}catch(error){toast(error.message);}});
  $('import-config').addEventListener('change',async e=>{try{const f=e.target.files[0];if(!f)return;if(f.size>60000)throw new Error('配置文件不能超过 60 KB。');await restore(JSON.parse(await f.text()));toast('配置已导入。');}catch(error){toast(error.message);}e.target.value='';});
  $('clear-overlay').addEventListener('click',()=>{clearSelectedFile();$('overlay-path').value='';update();toast('已清除本页选择；不会删除仓库中的文件。');});
  $('overlay-file').addEventListener('change',e=>{const file=e.target.files[0];if(!file)return;if(file.size>12*1024*1024||!/(\.zip|\.tgz|\.tar\.gz|\.7z)$/i.test(file.name)){e.target.value='';toast('请选择不超过 12 MiB 的 ZIP/TAR.GZ/TGZ/7Z。');return;}state.file=file;$('upload-label').textContent=`${file.name} · ${(file.size/1048576).toFixed(2)} MiB`;$('overlay-path').value='';update();});
  try{state.catalog=await json('data/catalog.json');$('version').replaceChildren(...state.catalog.versions.map(v=>new Option(state.catalog.version_labels?.[v]||`OpenWrt ${v}`,v)));$('version').value=state.catalog.default_version;
    $('metadata-date').textContent=`资料更新 ${new Date(state.catalog.updated).toLocaleDateString()}`;
    const devices=state.catalog.devices.filter(d=>d.version===val('version'));$('device-count').textContent=`${devices.length.toLocaleString()} 个设备档案`;
    let saved=null;try{if(checked('autofill'))saved=JSON.parse(localStorage.getItem('pb-current')||'null');}catch{}
    if(saved)try{await restore(saved);return;}catch{toast('原保存配置不适用于当前目录，已恢复默认。');}
    await selectDevice(devices.find(d=>d.target==='x86/64'&&d.id==='generic')||devices[0]);
  }catch(error){notice(`设备目录读取失败：${error.message}。请用 HTTP 服务器打开此网页，不要直接双击 HTML。`,'error');}
}
init().catch(error=>notice(`初始化失败：${error.message}`,'error'));
