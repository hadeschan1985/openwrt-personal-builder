import test from 'node:test';
import assert from 'node:assert/strict';
import {defaultConfig,safePreset} from '../site/lib/model.js';
import {boxProfile,boxErrors} from '../site/lib/box.js';
import {downloadLabel} from '../site/lib/delivery.js';

function config(){const c=defaultConfig('kwrt-25.12-20261012','armsr/armv8','box');c.output={...c.output,efi:false,legacy:false,rootfs:true,image_types:[]};c.box={model:'s905d',kernel:'stable-6.12.114'};return c;}
test('box selection survives template/history projection without arbitrary inputs',()=>{const c=config();c.box.token='private';assert.deepEqual(safePreset(c).box,{model:'s905d',kernel:'stable-6.12.114'});assert.equal(boxProfile(c),true);assert.equal(boxErrors(c).length,1);});
test('fixed box model/kernel pairing and ABI driver restrictions',()=>{const c=config(),catalog={models:[{id:'s905d',kernels:['stable-6.12.114']}]};assert.deepEqual(boxErrors(c,catalog),[]);c.box.kernel='stable-6.6.1';assert.match(boxErrors(c,catalog).join(),/DTB/);c.box.kernel='https://example.com/kernel';assert.match(boxErrors(c,catalog).join(),/固定/);c.box=config().box;c.features.usb_net=true;assert.match(boxErrors(c,catalog).join(),/驱动/);});
test('other devices cannot select a box kernel',()=>{const c=config();c.profile='generic';assert.match(boxErrors(c).join(),/盒子/);});
test('historical box versions survive reuse and reject another catalog',()=>{const c=config();c.box={model:'s905d',kernel:'rk3588-6.12.69',release:'box-20261027-1234abcd'};assert.deepEqual(safePreset(c).box,c.box);assert.deepEqual(boxErrors(c),[]);assert.match(boxErrors(c,{release:'box-20261027-deadbeef',models:[{id:'s905d',kernels:[c.box.kernel]}]}).join(),/DTB/);});
test('downloads distinguish actual box disks and OneCloud burn containers',()=>{assert.match(downloadLabel('personal-box-s905d-6.12.114.img.gz'),/Btrfs/);assert.match(downloadLabel('kwrt-amlogic-meson8b-thunder-onecloud-ext4-emmc_burn.img.gz'),/USB 烧录/);});
