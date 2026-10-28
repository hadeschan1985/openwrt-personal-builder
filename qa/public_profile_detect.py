"""Do not contact the private-cache-only platform in a public build campaign.

Its public baseline is used solely to retain the exclusion identity and count.
No cached OneCloud metadata is promoted or used to compile firmware here.
Every public platform still uses normal live discovery and checksum gates.
"""
import copy
from scripts import device_catalog as catalog,device_upstream as upstream,profile_campaign as campaign

def excluded_private_target(series):
    if series!='25.12':raise ValueError('Private-cache exclusion must be reviewed for a new release family')
    spec=copy.deepcopy(upstream.read('configs/builders.json')['kwrt-25.12-20261012']['targets']['amlogic/meson8b'])
    spec['source_cache']='onecloud-author-20261012'
    metadata=upstream.read('site/data/targets/kwrt-25.12-20261012/amlogic/meson8b.json')
    upstream.validate_metadata('amlogic/meson8b',spec,metadata)
    return 'amlogic/meson8b',spec,metadata

def detect():
    original=catalog.inspect
    def public_only(target,dynamic_issues=False,series='25.12'):
        if target=='amlogic/meson8b':return excluded_private_target(series)
        return original(target,dynamic_issues=dynamic_issues,series=series)
    try:
        catalog.inspect=public_only
        print('Private author-cache platform is excluded; its baseline identity is not an upstream refresh or compilation proof.',flush=True)
        campaign.detect()
    finally:catalog.inspect=original

if __name__=='__main__':detect()
