import json
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch
from scripts.build import ConfigError, password_hash, defaults_script, normalize

HASH='$6$testsalt$'+'a'*86

class PasswordHashTests(unittest.TestCase):
    def test_secret_uses_stdin_never_arguments(self):
        with patch('scripts.build.subprocess.run',return_value=subprocess.CompletedProcess([],0,HASH+'\n','')) as run:
            self.assertEqual(password_hash('fake-test-secret'),HASH)
            self.assertNotIn('fake-test-secret',' '.join(run.call_args.args[0]))
            self.assertEqual(run.call_args.kwargs['input'],'fake-test-secret\n')

    def test_failure_timeout_or_invalid_hash_never_falls_back_to_plaintext(self):
        for answer in [subprocess.CompletedProcess([],1,'','private diagnostics'),subprocess.CompletedProcess([],0,'plaintext',''),subprocess.CompletedProcess([],0,HASH+';bad','')]:
            with patch('scripts.build.subprocess.run',return_value=answer),self.assertRaises(ConfigError):password_hash('fake-secret')
        for error in [FileNotFoundError(),subprocess.TimeoutExpired('openssl',15)]:
            with patch('scripts.build.subprocess.run',side_effect=error),self.assertRaises(ConfigError):password_hash('fake-secret')

    def test_long_or_multiline_secret_rejected_before_starting_process(self):
        with patch('scripts.build.subprocess.run') as run:
            for value in ['','a'*129,'x\ny','x\ry','x\0y','中'*43]:
                with self.assertRaises(ConfigError):password_hash(value)
            run.assert_not_called()

    def test_only_salted_hash_is_embedded_in_generated_script(self):
        c=json.loads(Path('configs/x86-default.json').read_text());c['system']['password_secret']=True
        with patch('scripts.build.password_hash',return_value=HASH):script=defaults_script(normalize(c),{'ROUTER_PASSWORD':'never-embed-this-secret'})
        self.assertNotIn('never-embed-this-secret',script);self.assertIn(HASH,script)
        self.assertIn('s|^root:[^:]*:|root:',script);self.assertIn('chmod 600 /etc/shadow',script)

    @unittest.skipUnless(shutil.which('openssl'),'OpenSSL integration executes on Linux CI and real-image QA')
    def test_real_crypto_tool_produces_distinct_salts(self):
        first=password_hash('disposable-test-password');second=password_hash('disposable-test-password')
        self.assertNotEqual(first,second);self.assertTrue(first.startswith('$6$'))
