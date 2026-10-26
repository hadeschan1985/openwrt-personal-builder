import test from 'node:test';
import assert from 'node:assert/strict';
import {defaultConfig,safePreset,deviceOutput,validate,deviceMatches,upgradeAutofill} from '../site/lib/model.js';
import {firmwareArtifact,firmwareFile,deliveryLabel,artifactFile,downloadLabel} from '../site/lib/delivery.js';

test('new device configuration selects root explicitly and integrity-only delivery',()=>{
  const c=defaultConfig('kwrt-25.12-20261012','mediatek/filogic','xiaomi_redmi-router-ax6000');
  assert.equal(c.build_mode,'device');assert.equal(c.system.password_source,'root');assert.deepEqual(validate(c),[]);
});
test('old configurations do not silently change their password source or image selection',()=>{
  const c=defaultConfig();delete c.system.password_source;assert.equal(safePreset(c).system.password_source,undefined);assert.equal(safePreset(c).output.image_types,undefined);
  c.output.image_types=['sysupgrade-v7'];assert.deepEqual(safePreset(c).output.image_types,c.output.image_types);
});
test('default device format prioritizes sysupgrade and ignores bare bootloaders',()=>{
  assert.deepEqual(deviceOutput([{name:'boot.fip',type:'bootloader',filesystem:''},{name:'factory.bin',type:'factory',filesystem:'squashfs'},{name:'upgrade.bin',type:'sysupgrade',filesystem:'squashfs'}]),{filesystem:'squashfs',image_types:['sysupgrade']});
  assert.throws(()=>deviceOutput([]));
});
test('individual device downloads are recognized without treating reports as firmware',()=>{
  assert.ok(firmwareArtifact({name:'firmware-99-device-32'}));assert.ok(!firmwareArtifact({name:'firmware-99-device-33'}));
  for(const name of ['upgrade.itb','sysupgrade.bin','device.trx','emmc.img','sysupgrade.tar'])assert.ok(firmwareFile(name));
  assert.ok(!firmwareFile('image-report.json'));assert.match(deliveryLabel({config:{build_mode:'device'},image_validation:{status:'passed'}}),/未验证开机/);
});
test('Chinese brands and multiple query words find the corresponding models',()=>{
  const d={name:'Xiaomi Redmi Router AX6000',target:'mediatek/filogic',id:'xiaomi_redmi-router-ax6000',aliases:[]};
  assert.ok(deviceMatches(d,'红米 ax6000'));assert.ok(deviceMatches(d,'小米 6000'));assert.ok(!deviceMatches(d,'华硕 6000'));
});
test('old automatic drafts adopt requested root default without changing imported historical records',()=>{
  const c=defaultConfig();delete c.system.password_source;c.system.password_secret=false;
  assert.equal(upgradeAutofill(c).system.password_source,'root');assert.equal(upgradeAutofill(c).system.password_secret,true);assert.equal(safePreset(c).system.password_source,undefined);
  c.system.password_source='secret';assert.equal(upgradeAutofill(c).system.password_source,'secret');
});
test('device download numbers resolve to the correct file and format of the same build',()=>{
  const first={name:'router-factory.bin',group:'device'},second={name:'router-sysupgrade.bin',group:'device'};
  const record={run_number:'9',files:[{name:'report.json',group:'reports'},first,second]};
  assert.equal(artifactFile({name:'firmware-9-device-01'},record),first);assert.equal(artifactFile({name:'firmware-9-device-02'},record),second);
  assert.equal(artifactFile({name:'firmware-8-device-01'},record),null);assert.equal(artifactFile({name:'firmware-9-device-03'},record),null);
  assert.match(downloadLabel(first.name),/^factory/);assert.match(downloadLabel(second.name),/^sysupgrade/);
});
