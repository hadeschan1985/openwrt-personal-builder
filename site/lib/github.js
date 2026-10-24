const API='https://api.github.com';
export function repositoryName(value) {
  if(!/^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})\/[A-Za-z0-9_.-]+$/.test(value))throw new Error('仓库格式应为 owner/repository。');
  return value;
}
export class GitHub {
  constructor(repo,token,ref='main',fetcher=fetch) {
    this.repo=repositoryName(repo);this.token=token;this.ref=ref;this.fetcher=fetcher;
    if(!/^[A-Za-z0-9_./-]+$/.test(ref)||ref.includes('..'))throw new Error('分支名无效。');
  }
  async request(path,options={}) {
    const headers={'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28',...(options.body?{'Content-Type':'application/json'}:{})};
    if(this.token)headers.Authorization=`Bearer ${this.token}`;
    const r=await this.fetcher(`${API}/repos/${this.repo}${path}`,{...options,headers,cache:'no-store'});
    if(!r.ok){let message='';try{message=(await r.json()).message||'';}catch{}throw new Error(`GitHub ${r.status}：${message||'请求失败，请检查仓库与授权。'}`);}
    return r.status===204?null:r.json();
  }
  async connect(){const data=await this.request('');this.private=data.private;this.defaultBranch=data.default_branch;return data;}
  async dispatch(config,requestId) {
    if(!this.token)throw new Error('直接启动构建需要仓库 Actions 写入授权。');
    const serialized=JSON.stringify(config);
    if(new TextEncoder().encode(serialized).length>60000)throw new Error('配置超过 60 KB。');
    await this.request('/actions/workflows/build.yml/dispatches',{method:'POST',body:JSON.stringify({ref:this.ref,inputs:{config_json:serialized,request_id:requestId}})});
  }
  runs(){return this.request('/actions/workflows/build.yml/runs?per_page=12');}
  artifacts(runId){if(!/^\d+$/.test(String(runId)))throw new Error('任务 ID 无效');return this.request(`/actions/runs/${runId}/artifacts`);}
  async upload(file) {
    if(!this.private)throw new Error('文件包只能上传到已连接的私有构建仓库。');
    if(file.size>12*1024*1024)throw new Error('文件包不能超过 12 MiB。');
    const name=file.name.toLowerCase();
    const extension=name.endsWith('.tar.gz')?'tar.gz':name.split('.').pop();
    if(!['zip','tgz','tar.gz'].includes(extension))throw new Error('目前支持 ZIP/TAR.GZ/TGZ。');
    const bytes=new Uint8Array(await file.arrayBuffer());
    const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(n=>n.toString(16).padStart(2,'0')).join('');
    const path=`overlays/${hash.slice(0,24)}.${extension}`;
    let binary='';for(let i=0;i<bytes.length;i+=32768)binary+=String.fromCharCode(...bytes.subarray(i,i+32768));
    let exists=false;try{const old=await this.request(`/contents/${path}?ref=${encodeURIComponent(this.ref)}`);exists=Boolean(old.sha);}catch(error){if(!error.message.startsWith('GitHub 404'))throw error;}
    if(!exists)await this.request(`/contents/${path}`,{method:'PUT',body:JSON.stringify({message:'Add personal firmware overlay',content:btoa(binary),branch:this.ref})});
    return path;
  }
}
