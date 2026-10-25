import io
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts.build import manifest_packages, dependency_preflight, ConfigError, run_logged


class PreflightTests(unittest.TestCase):
    def test_manifest_parser_rejects_commands(self):
        self.assertEqual(manifest_packages('make install\ncurl - 8.0-r1\nfoo - bar baz\nlibc - 1.2\n'), {'curl', 'libc'})

    def test_resolver_missing_and_readded_packages_fail_early(self):
        with patch('scripts.build.run_logged', return_value=(0, 'curl - 1\n')):
            with self.assertRaisesRegex(ConfigError, '未找到.*xray-core'):
                dependency_preflight(Path('.'), 'generic', ['xray-core'], io.StringIO(), [])
            with self.assertRaisesRegex(ConfigError, '重新加入.*curl'):
                dependency_preflight(Path('.'), 'generic', ['-curl'], io.StringIO(), [])

    def test_resolver_failure_cannot_continue_to_images(self):
        with patch('scripts.build.run_logged', return_value=(2, 'download error')) as runner:
            with self.assertRaisesRegex(ConfigError, '尚未生成映像'):
                dependency_preflight(Path('.'), 'generic', ['curl'], io.StringIO(), [])
            self.assertEqual(runner.call_args.args[0][:2], ['make', 'manifest'])
            self.assertFalse(any(arg.startswith('FILES=') for arg in runner.call_args.args[0]))

    def test_log_redacts_all_secret_values(self):
        class Process:
            stdout = ['contains private-password\n']
            def wait(self): return 0
        log = io.StringIO()
        with patch('scripts.build.subprocess.Popen', return_value=Process()):
            code, text = run_logged(['make', 'manifest'], Path('.'), log, ['private-password'])
        self.assertEqual(code, 0)
        self.assertNotIn('private-password', log.getvalue() + text)


if __name__ == '__main__': unittest.main()
