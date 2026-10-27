import io
import http.client
import unittest
from unittest.mock import patch
from scripts import catalog


def response(raw, length=None):
    stream=io.BytesIO(raw);stream.headers={'Content-Length':str(len(raw) if length is None else length)};return stream


class CatalogTransportTests(unittest.TestCase):
    def test_short_response_is_retried_with_a_fresh_complete_response(self):
        with patch.object(catalog.urllib.request,'urlopen',side_effect=[response(b'{',7),response(b'{"a":1}')]) as opened,patch.object(catalog.time,'sleep'):
            self.assertEqual(catalog.get_json('https://example.invalid'),{'a':1});self.assertEqual(opened.call_count,2)

    def test_invalid_json_404_and_oversized_data_fail_without_retry(self):
        for data,error in ((response(b'invalid'),ValueError),(response(b'12345'),ValueError)):
            with patch.object(catalog.urllib.request,'urlopen',return_value=data) as opened,patch.object(catalog.time,'sleep') as sleep:
                with self.assertRaises(error):catalog.get_json('https://example.invalid') if data.getvalue()==b'invalid' else catalog.fetch_bytes('https://example.invalid',limit=4)
                self.assertEqual(opened.call_count,1);sleep.assert_not_called()
        with patch.object(catalog.urllib.request,'urlopen',side_effect=catalog.urllib.error.HTTPError('https://example.invalid',404,'missing',{},None)) as opened:
            with self.assertRaises(catalog.urllib.error.HTTPError):catalog.get_json('https://example.invalid')
            self.assertEqual(opened.call_count,1)

    def test_repeated_incomplete_reads_stop_after_three_attempts(self):
        with patch.object(catalog.urllib.request,'urlopen',side_effect=[response(b'x',2) for _ in range(3)]) as opened,patch.object(catalog.time,'sleep') as sleep:
            with self.assertRaises(http.client.IncompleteRead):catalog.fetch_bytes('https://example.invalid')
            self.assertEqual(opened.call_count,3);self.assertEqual(sleep.call_count,2)
