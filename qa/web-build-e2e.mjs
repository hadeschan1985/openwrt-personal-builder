// Real browser + real GitHub API. No mocked dispatches, records or firmware.
// The test browser is local to an isolated Actions runner, not the user's PC.
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {spawn,execFileSync} from 'node:child_process';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';

const {chromium}=await import(pathToFileURL(resolve('work/web-e2e/node_modules/playwright/index.mjs')).href);
const token=process.env.GH_TOKEN,repo=process.env.GITHUB_REPOSITORY;
assert(token&&/^[A-Za-z0-9-]+\/[A-Za-z0-9_.-]+$/.test(repo));
const root=resolve('work/web-e2e');await mkdir(root,{recursive:true});
const server=spawn('python',['-m','http.server','8771','--bind','127.0.0.1','--directory','site'],{stdio:'ignore'});
const pause=ms=>new Promise(r=>setTimeout(r,ms));
async function api(path){const response=await fetch(`https://api.github.com/repos/${repo}${path}`,{headers:{Authorization:`Bearer ${token}`,Accept:'application/vnd.github+json'}});assert(response.ok,`GitHub API ${response.status}`);return response.json();}
const approved=JSON.parse(await readFile('updates/devices-approved.json','utf8'));
const template=JSON.parse(await readFile('configs/x86-default.json','utf8'));
const boxApproved=JSON.parse(await readFile('updates/box-approved.json','utf8'));
const cases=[{id:'onecloud',target:'amlogic/meson8b',profile:'thunder-onecloud',filesystem:'ext4',types:['emmc_burn']},{id:'box',target:'armsr/armv8',profile:'box',box:{model:'s905x3-hk1',kernel:'stable-6.12.114'},filesystem:'squashfs',types:[]},{id:'wavlink',target:'mediatek/filogic',profile:'wavlink_wl-wn573hx3',official:true,filesystem:'squashfs',types:['WN573HX3-sysupgrade']}];
const selectedCase=process.env.WEB_E2E_CASE;
assert(!selectedCase||cases.some(test=>test.id===selectedCase),'Unknown browser acceptance case');
const browser=await chromium.launch({headless:true});const page=await browser.newPage({acceptDownloads:true});
const reports=[];
try{
  for(let n=0;n<50;n++){try{if((await fetch('http://127.0.0.1:8771')).ok)break;}catch{}await pause(100);}
  await page.goto('http://127.0.0.1:8771/',{waitUntil:'domcontentloaded'});
  await page.locator('#device-search:not([disabled])').waitFor();
  await page.locator('#connect-button').click();await page.locator('#repository').fill(repo);await page.locator('#github-token').fill(token);await page.locator('#confirm-connect').click();
  await page.locator('#connect-dialog').waitFor({state:'hidden',timeout:60000});
  for(const test of cases.filter(test=>!selectedCase||test.id===selectedCase)){
    const config=structuredClone(template);Object.assign(config,{builder:test.official?'official':'kwrt',version:test.official?'25.12.6':approved.version,target:test.target,profile:test.profile,build_mode:'device',packages:['curl']});
    Object.assign(config.system,{hostname:'E2E-'+test.id,password_secret:true,password_source:'root'});
    Object.assign(config.output,{filesystem:test.filesystem,image_types:test.types,rootfs:Boolean(test.box),efi:false,legacy:false,vmdk:false,rootfs_size_mb:256});
    if(test.box){const model=boxApproved.models.find(m=>m.id===test.box.model);config.box={...test.box,kernel:model.kernels.filter(k=>k.startsWith('stable-')).sort((a,b)=>b.localeCompare(a,undefined,{numeric:true}))[0],release:boxApproved.release};}
    const input=resolve(root,test.id+'.json');await writeFile(input,JSON.stringify(config));
    await page.locator('#import-config').setInputFiles(input);
    await page.waitForFunction(p=>document.querySelector('#device-platform').textContent.includes(p),test.profile,{timeout:60000});
    await page.locator('#build-button:not([disabled])').waitFor({timeout:60000});
    const dispatch=page.waitForResponse(r=>r.url().endsWith('/actions/workflows/build.yml/dispatches')&&r.request().method()==='POST',{timeout:90000});
    await page.locator('#build-button').click();const response=await dispatch;assert.equal(response.status(),204,'Page dispatch was not accepted');
    const body=response.request().postDataJSON(),request=body.inputs.request_id;assert.match(request,/^[a-f0-9-]{36}$/);assert.equal(JSON.parse(body.inputs.config_json).profile,test.profile);
    let run;const deadline=Date.now()+55*60*1000;
    while(Date.now()<deadline){const data=await api('/actions/workflows/build.yml/runs?per_page=30');run=data.workflow_runs.find(r=>r.display_title.endsWith(request));if(run?.status==='completed')break;await pause(15000);}
    assert(run?.status==='completed'&&run.conclusion==='success',`Actual ${test.id} build failed or timed out: ${run?.id}`);
    await page.locator('#refresh-results').click();
    await page.locator('#latest-results').getByRole('button',{name:'用此配置重新填写',exact:true}).waitFor({timeout:60000});
    await page.waitForFunction(({profile,number})=>{const text=document.querySelector('#latest-results')?.textContent||'';return text.includes(`构建 #${number} · 编译成功`)&&text.includes(`结果设备：`)&&text.includes(profile);},{profile:test.profile,number:run.run_number},{timeout:60000});
    const child=execFileSync('python',['-m','scripts.e2e_artifact','--run',String(run.id),'--destination',resolve(root,test.id)],{encoding:'utf8',maxBuffer:1024*1024});
    const download=JSON.parse(child.split('\n').find(l=>l.startsWith('E2E_DOWNLOAD=')).slice(13));
    const card=page.locator('#latest-results .artifact').filter({hasText:`firmware-${run.run_number}-device-01`});
    const href=await card.getByRole('link').first().getAttribute('href');assert(href.includes(String(download.artifact_id)),'Homepage download links to a different artifact');
    const row=page.locator('#latest-results tr').filter({hasText:download.file.name});await row.getByRole('button',{name:'校验此文件',exact:true}).click();
    await page.locator('#verify-file').setInputFiles(download.raw);await page.getByText('校验通过：文件大小及 SHA256 与对应记录一致。',{exact:true}).waitFor({timeout:180000});
    await page.locator('#verify-dialog').getByRole('button',{name:'关闭',exact:true}).click();
    await page.locator('#latest-results').getByRole('button',{name:'用此配置重新填写',exact:true}).click();await page.getByText('配置已填写，尚未提交构建；后台密码使用所选来源。',{exact:true}).waitFor({timeout:60000});
    await page.locator('#preview-button').click();const restored=JSON.parse(await page.locator('#config-json').inputValue());await page.locator('#config-dialog').getByRole('button',{name:'关闭',exact:true}).click();
    for(const key of ['builder','version','target','profile','system','output','packages','box'])assert.deepEqual(restored[key],download.config[key],`Reused ${key} changed`);
    const screenshot=resolve(root,test.id+'-success.png');await page.locator('#latest-results').scrollIntoViewIfNeeded();await page.screenshot({path:screenshot});
    reports.push({case:test.id,status:'passed',run_id:run.id,run_number:run.run_number,request_id:request,dispatch:'real-page-HTTP-204',homepage_artifact_id:download.artifact_id,download_sha256:download.file.sha256,browser_file_verification:'passed',configuration_reuse:'exact',source_commit:run.head_sha,screenshot:test.id+'-success.png',hardware_tested:false});
    console.log('WEB_E2E_CASE='+JSON.stringify(reports.at(-1)));
    const offlineDispatch=page.waitForResponse(r=>r.url().endsWith('/actions/workflows/build.yml/dispatches')&&r.request().method()==='POST');
    await page.locator('#latest-results').getByRole('button',{name:'用归档软件离线重建',exact:true}).click();
    const offlineAccepted=await offlineDispatch;assert.equal(offlineAccepted.status(),204,'Archived rebuild dispatch failed');
    const offlineInputs=offlineAccepted.request().postDataJSON().inputs;assert.equal(offlineInputs.rebuild_run_id,String(run.id));
    let offlineRun;for(let attempt=0;attempt<200;attempt++){const data=await api('/actions/workflows/build.yml/runs?per_page=12');offlineRun=data.workflow_runs.find(r=>r.display_title.endsWith(' · '+offlineInputs.request_id));if(offlineRun?.status==='completed')break;await pause(15000);}
    assert(offlineRun?.conclusion==='success',`Offline ${test.id} rebuild failed: ${offlineRun?.id}`);
    const offlineRecordResponse=await api(`/contents/records/${offlineRun.id}.json`);const offlineRecord=JSON.parse(Buffer.from(offlineRecordResponse.content,'base64').toString('utf8'));
    assert.deepEqual(offlineRecord.config,download.config,'Offline rebuild changed the original configuration');assert.equal(offlineRecord.rebuild.engine_source_commit,run.head_sha);
    const recordFile=offlineRecord.files.find(f=>f.name==='rebuild-report.json');assert(recordFile,'Offline rebuild report missing');
    reports.push({case:test.id+'-offline',status:'passed',run_id:offlineRun.id,original_run_id:run.id,configuration_reuse:'exact',network:'Linux network namespace disabled',package_versions:'exact manifest equality enforced',archived_engine_source_commit:offlineRecord.rebuild.engine_source_commit,hardware_tested:false});
    console.log('WEB_E2E_CASE='+JSON.stringify(reports.at(-1)));
  }
  const sourceHash=createHash('sha256').update(await readFile('site/app.js')).digest('hex');await writeFile(resolve(root,'report.json'),JSON.stringify({schema_version:1,status:'passed',run_id:process.env.GITHUB_RUN_ID,source_commit:process.env.GITHUB_SHA,web_app_sha256:sourceHash,cases:reports},null,2));
}catch(error){console.error(String(error.stack||error).replaceAll(token,'***'));await writeFile(resolve(root,'failure.json'),JSON.stringify({status:'failed',passed_cases:reports,error:String(error.message||error).replaceAll(token,'***')}));process.exitCode=1;}
finally{await browser.close();server.kill();}
