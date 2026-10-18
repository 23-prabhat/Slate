import unittest
from folio_notepad.ai import StreamDecoder

class StreamTests(unittest.TestCase):
    def test_stream_split_in_utf8_sequence(self):
        d=StreamDecoder()
        text='{"response":"नमस्ते","done":false}\n{"response":"!","done":true}'.encode()
        parts=[text[:20],text[20:23],text[23:40],text[40:]]
        output=''.join(d.feed(p,i==len(parts)-1) for i,p in enumerate(parts))
        self.assertEqual(output,'नमस्ते!'); self.assertTrue(d.done)
    def test_provider_error(self):
        with self.assertRaises(ValueError): StreamDecoder().feed(b'{"error":"missing model"}\n')
    def test_response_limit(self):
        with self.assertRaises(ValueError): StreamDecoder().feed(b'x'*(4*1024*1024+1))
