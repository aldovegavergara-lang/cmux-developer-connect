#!/usr/bin/env python3
"""Real TLS admission and closed app policy; native behavior is verified separately."""
import base64
import importlib.util
import http.client
import json
import pathlib
import secrets
import ssl
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid

root=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('developer_peer',root/'Resources/bin/cmux-peer-service.py')
peer=importlib.util.module_from_spec(spec); spec.loader.exec_module(peer)

class Broker:
    def catalog(self): return {'workspaces':[{'id':'HOST','terminals':[]}]}
    def replay(self,body): return {'workspace_id':body['workspace_id']}
    def input(self,body,admission=None):
        if admission: admission()
        return {'accepted':True}
    def action(self,body,admission=None):
        if admission: admission()
        return {'accepted':True}

class Peers(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='cmux-peer-test-')
        self.folder=str(pathlib.Path(self.temp.name).resolve())
        self.grants=peer.Grants(self.folder)
        cert,key=peer.certificate(self.folder,'127.0.0.1')
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(cert,key)
        self.server=peer.PeerServer(('127.0.0.1',0),context,Broker(),self.grants,'test-host','Host')
        self.worker=threading.Thread(target=self.server.serve_forever,daemon=True); self.worker.start()
        self.url='https://127.0.0.1:'+str(self.server.server_port)
        self.context=ssl.create_default_context(cafile=str(cert))
    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.worker.join(); self.temp.cleanup()
    def call(self,path,body=None,token=None,context=None,origin=None):
        headers={}
        if token: headers['Authorization']='Bearer '+token
        if body is not None: headers['Content-Type']='application/json'
        if origin: headers['Origin']=origin
        request=urllib.request.Request(self.url+path,None if body is None else json.dumps(body).encode(),headers)
        try:
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),urllib.request.HTTPSHandler(context=context or self.context))
            with opener.open(request,timeout=3) as response:
                return response.status,json.load(response)
        except urllib.error.HTTPError as error:
            with error: return error.code,json.load(error)
    def pair(self):
        invitation,_=self.grants.invite(); client=str(uuid.uuid4())
        status,result=self.call('/v1/pair',{'invitation':invitation,'client_id':client,'name':'Client'})
        self.assertEqual(status,200)
        return client,result['result']['token'],invitation
    def test_tls_required_and_no_untrusted_certificate(self):
        with self.assertRaises(urllib.error.URLError): self.call('/v1/catalog',context=ssl.create_default_context())
        self.assertEqual(self.call('/v1/catalog')[0],401)
        self.assertEqual(self.call('/v1/catalog',token='wrong')[0],401)
    def test_pair_single_use_revocation_and_persistence(self):
        client,token,invitation=self.pair()
        self.assertEqual(self.call('/v1/catalog',token=token)[0],200)
        self.assertEqual(self.call('/v1/pair',{'invitation':invitation,'client_id':str(uuid.uuid4()),'name':'Other'})[0],401)
        reloaded=peer.Grants(self.folder)
        self.assertTrue(reloaded.authorize(token))
        self.grants.revoke(client)
        self.assertEqual(self.call('/v1/catalog',token=token)[0],401)
        self.assertFalse(peer.Grants(self.folder).authorize(token))
    def test_pair_expiration_and_browser_origin(self):
        invitation,_=self.grants.invite()
        self.grants.invitation=(self.grants.invitation[0],time.monotonic()-1)
        self.assertEqual(self.call('/v1/pair',{'invitation':invitation,'client_id':str(uuid.uuid4()),'name':'Client'})[0],401)
        _,token,_=self.pair()
        self.assertEqual(self.call('/v1/catalog',token=token,origin='https://evil.example')[0],403)
        self.assertEqual(self.call('/v1/rpc',{'method':'surface.respawn'},token)[0],404)
    def test_private_bind_and_file_permissions(self):
        for address in ['0.0.0.0','8.8.8.8','192.0.2.1','::1']: self.assertFalse(peer.private_address(address))
        self.assertTrue(peer.private_address('192.168.0.2'))
        self.assertFalse(peer.private_address('100.64.0.1'))
        self.assertTrue(peer.private_address('100.64.0.1',True))
        self.pair()
        self.assertEqual(self.grants.path.stat().st_mode & 0o777,0o600)
    def test_closed_actions_and_target_membership(self):
        broker=object.__new__(peer.OwnerBroker)
        class RPC:
            def __init__(self): self.calls=[]
            def rpc(self,method,params): self.calls.append((method,params)); return {'ok':True}
        broker.local=RPC()
        wid,sid,other=(str(uuid.uuid4()).upper() for _ in range(3))
        broker.catalog=lambda fresh=False:{'peer_input_epoch_guard':True,'workspaces':[{'id':wid,'terminals':[{'id':sid}]}]}
        with self.assertRaises(peer.PeerError): broker.input({'workspace_id':wid,'surface_id':other,'text':'x'})
        with self.assertRaises(peer.PeerError): broker.action({'action':'workspace.new','command':'rm -rf /'})
        with self.assertRaises(peer.PeerError): broker.action({'action':'surface.respawn','workspace_id':wid})
        with self.assertRaises(peer.PeerError): broker.action({'action':'workspace.close','workspace_id':wid})
        self.assertEqual(broker.local.calls,[])
        broker.input({'workspace_id':wid,'surface_id':sid,'text':'echo okay\r','expected_render_epoch':'epoch-1'})
        self.assertEqual(broker.local.calls[0][0],'mobile.terminal.input')
        broker.action({'action':'workspace.new','title':'New'})
        self.assertNotIn('initial_command',broker.local.calls[-1][1])

    def test_files_are_read_only_and_cannot_follow_symlinks(self):
        folder=pathlib.Path(self.folder)/'work'; folder.mkdir()
        (folder/'safe.txt').write_text('safe')
        outside=pathlib.Path(self.folder)/'private.txt'; outside.write_text('secret')
        (folder/'link').symlink_to(outside)
        (folder/'parent-link').symlink_to(folder.parent,target_is_directory=True)
        wid,sid=(str(uuid.uuid4()).upper() for _ in range(2))
        broker=object.__new__(peer.OwnerBroker)
        broker.catalog=lambda fresh=False:{'workspaces':[{'id':wid,'terminals':[{'id':sid,'current_directory':str(folder)}]}]}
        request={'workspace_id':wid,'surface_id':sid,'operation':'read'}
        result=broker.files(dict(request,path=str(folder/'safe.txt')))
        self.assertEqual(base64.b64decode(result['data_b64']),b'safe')
        for path in [outside,folder/'../private.txt',folder/'link',folder/'parent-link/private.txt']:
            with self.assertRaises(peer.PeerError): broker.files(dict(request,path=str(path)))
        with self.assertRaises(peer.PeerError): broker.files(dict(request,path=str(folder/'safe.txt'),operation='write'))
        (folder/'large').write_bytes(b'x'*(2*1024*1024+1))
        with self.assertRaises(peer.PeerError): broker.files(dict(request,path=str(folder/'large')))

    def test_invitation_rate_limit_and_expired_credentials(self):
        invitation,_=self.grants.invite()
        for _ in range(5):
            self.assertEqual(self.call('/v1/pair',{'invitation':'wrong','client_id':str(uuid.uuid4()),'name':'Client'})[0],401)
        self.assertEqual(self.call('/v1/pair',{'invitation':invitation,'client_id':str(uuid.uuid4()),'name':'Client'})[0],429)
        self.grants.failures={}
        client,token,_=self.pair()
        self.grants.peers[client.upper()]['expires_at']=time.time()-1
        self.assertEqual(self.call('/v1/catalog',token=token)[0],401)

    def test_old_owner_without_producer_guard_is_read_only(self):
        broker=object.__new__(peer.OwnerBroker)
        wid,sid=(str(uuid.uuid4()).upper() for _ in range(2))
        broker.catalog=lambda fresh=False:{'workspaces':[{'id':wid,'terminals':[{'id':sid}]}]}
        with self.assertRaises(peer.PeerError):
            broker.input({'workspace_id':wid,'surface_id':sid,'text':'x','expected_render_epoch':'old'})

    def test_persistent_tls_connection_rechecks_revocation(self):
        client,token,_=self.pair()
        connection=http.client.HTTPSConnection('127.0.0.1',self.server.server_port,context=self.context,timeout=3)
        try:
            connection.request('GET','/v1/catalog',headers={'Authorization':'Bearer '+token})
            response=connection.getresponse(); response.read()
            self.assertEqual(response.status,200)
            self.assertEqual(response.getheader('Connection'),'keep-alive')
            self.assertIsNotNone(connection.sock)
            self.grants.revoke(client)
            connection.request('GET','/v1/catalog',headers={'Authorization':'Bearer '+token})
            response=connection.getresponse(); response.read()
            self.assertEqual(response.status,401)
        finally: connection.close()

if __name__=='__main__': unittest.main()
