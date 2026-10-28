import unittest
from unittest.mock import patch
from qa.public_profile_detect import detect,excluded_private_target
from scripts import device_catalog as catalog

class PublicProfileDetectTest(unittest.TestCase):
    def test_private_cache_baseline_only_identifies_an_excluded_profile(self):
        target,spec,metadata=excluded_private_target('25.12')
        self.assertEqual(target,'amlogic/meson8b');self.assertEqual(spec['source_cache'],'onecloud-author-20261012');self.assertIn('blocked_reason',spec);self.assertEqual(list(metadata['profiles']['profiles']),['thunder-onecloud'])
        with self.assertRaises(ValueError):excluded_private_target('26.12')
    def test_public_discovery_errors_propagate_and_original_function_is_restored(self):
        def inspect(target,**kwargs):raise OSError('public source unavailable')
        def campaign():
            self.assertEqual(catalog.inspect('amlogic/meson8b')[0],'amlogic/meson8b')
            catalog.inspect('mediatek/filogic')
        with patch.object(catalog,'inspect',inspect),patch('qa.public_profile_detect.campaign.detect',campaign):
            with self.assertRaisesRegex(OSError,'public source'):detect()
            self.assertIs(catalog.inspect,inspect)
