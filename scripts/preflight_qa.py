"""A real solver rejection must stop before image generation; disposable CI only."""
import json
from pathlib import Path
from scripts.build import build, normalize, ConfigError, require


def main():
    raw = json.loads(Path('configs/x86-default.json').read_text(encoding='utf-8'))
    raw['packages'] = ['personal-qa-missing-package-do-not-publish']
    try:
        build(normalize(raw))
    except ConfigError as error:
        require('依赖预检失败' in str(error), 'Negative QA failed at an unexpected stage')
        require(not list(Path('outputs').glob('*.img*')), 'Image generated despite failed preflight')
        report = {'status': 'passed', 'expected_failure': 'dependency-preflight', 'images_generated': False}
        Path('work/preflight-negative.json').write_text(json.dumps(report), encoding='utf-8')
        print('Expected dependency rejection verified; no image generated.')
        return
    raise AssertionError('Nonexistent package unexpectedly passed')


if __name__ == '__main__': main()
