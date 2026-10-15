import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs,urlparse
from chatgpt_connection import ChatGPTConnection, StudyError, private_write


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'auth'
        self.service=ChatGPTConnection(self.root,8767)

    def test_pkce_host_persistence_and_expiring_state(self):
        a=parse_qs(urlparse(self.service.authorize()).query)
        b=parse_qs(urlparse(self.service.authorize()).query)
        self.assertEqual(a['ext_agent_host_id'],b['ext_agent_host_id'])
        self.assertNotEqual(a['state'],b['state'])
        self.assertEqual(a['code_challenge_method'],['S256'])
        self.assertEqual(a['redirect_uri'],['http://127.0.0.1:8767/oauth/chatgpt/callback'])
        with self.assertRaises(StudyError): self.service.callback({'state':a['state']})
        self.service.pending['expires']=0
        with self.assertRaises(StudyError): self.service.callback({'state':b['state']})

    def test_denial_consumes_pending_attempt(self):
        q=parse_qs(urlparse(self.service.authorize()).query)
        with self.assertRaises(StudyError): self.service.callback({'state':q['state'],'error':['access_denied']})
        self.assertIsNone(self.service.pending)

    def test_wrong_nonce_never_activates_account(self):
        q=parse_qs(urlparse(self.service.authorize()).query)
        self.service.token_request=Mock(return_value={'id_token':'fake','access_token':'fake'})
        with patch('chatgpt_connection.jwt.PyJWKClient'),patch('chatgpt_connection.jwt.decode',return_value={'nonce':'wrong','sub':'demo'}):
            with self.assertRaises(StudyError):self.service.callback({'state':q['state'],'client_id':['oaiapp_demo'],'code':['fake']})
        self.assertFalse(self.service.status()['connected'])
        self.assertNotIn('fake',(self.root/'accounts.json').read_text())

    def test_signature_failure_never_activates(self):
        q=parse_qs(urlparse(self.service.authorize()).query)
        self.service.token_request=Mock(return_value={'id_token':'fake','access_token':'fake'})
        with patch('chatgpt_connection.jwt.PyJWKClient',side_effect=ValueError('invalid')):
            with self.assertRaises(StudyError):self.service.callback({'state':q['state'],'client_id':['oaiapp_demo'],'code':['fake']})
        self.assertFalse(self.service.status()['connected'])

    def test_identity_only_blocks_inference(self):
        private_write(self.root/'accounts.json',{'active':'demo','accounts':{'demo':{'access_token':'secret','scopes':['openid']}}})
        with self.assertRaises(StudyError):self.service.access()
        self.assertNotIn('secret',json.dumps(self.service.status()))
        self.assertEqual((self.root/'accounts.json').stat().st_mode & 0o777,0o600)

    def test_refresh_rotation(self):
        private_write(self.root/'accounts.json',{'active':'demo','accounts':{'demo':{'access_token':'old','refresh_token':'refresh','scopes':['chatgpt.tokens.use.direct'],'expires_at':0}}})
        self.service.token_request=Mock(return_value={'access_token':'new','refresh_token':'rotated','expires_in':3600})
        self.assertEqual(self.service.access(),'new')
        self.assertEqual(self.service.load()['accounts']['demo']['refresh_token'],'rotated')
        self.assertNotIn('scope',self.service.token_request.call_args.args[0])

    def stream(self,events):
        response=Mock();response.status_code=200
        response.iter_lines.return_value=[b'data: '+json.dumps(x).encode() for x in events]
        self.service.http=Mock()
        self.service.http.post.return_value.__enter__=Mock(return_value=response)
        self.service.http.post.return_value.__exit__=Mock(return_value=False)
        self.service.models=Mock(return_value=[{'id':'demo'}]);self.service.access=Mock(return_value='fake')
        return response

    def test_only_completed_stream_succeeds(self):
        self.stream([{'type':'response.output_text.delta','delta':'answer'},{'type':'response.completed'}])
        self.assertEqual(self.service.complete('demo','instructions','prompt'),'answer')
        payload=self.service.http.post.call_args.kwargs['json']
        self.assertFalse(payload['store']);self.assertTrue(payload['stream'])
        self.stream([{'type':'response.output_text.delta','delta':'partial'},{'type':'response.failed'}])
        with self.assertRaises(StudyError):self.service.complete('demo','instructions','prompt')
        self.stream([{'type':'response.output_text.delta','delta':'partial'}])
        with self.assertRaises(StudyError):self.service.complete('demo','instructions','prompt')
