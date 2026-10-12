#!/usr/bin/env python3
"""Opt-in paired HTTPS access to a running Developer app, without session migration."""
import argparse
import base64
import hashlib
import hmac
import http.server
import ipaddress
import json
import os
import pathlib
import secrets
import signal
import socket
import ssl
import subprocess
import sys
import threading
import time
import uuid
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'peer'))
from policy import OwnerBroker, PeerError, fields, identifier, private_address, private_folder, text
from http_limits import BoundedServerMixin, BoundedRequestMixin, strict_json

MAX_BODY=32768

def write_private(path,value):
    temporary=str(path)+'.'+secrets.token_hex(6)
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as handle:
        json.dump(value,handle); handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary,path)

def private_json(path,default):
    if not os.path.exists(path): return default
    info=os.lstat(path)
    if info.st_uid!=os.getuid() or info.st_mode & 0o077 or os.path.islink(path):
        raise PeerError('unsafe_state','Private file has unsafe ownership or permissions')
    return json.loads(pathlib.Path(path).read_text())

class Grants:
    def __init__(self,folder):
        self.folder=pathlib.Path(private_folder(folder))
        self.path=self.folder/'grants.json'
        self.lock=threading.RLock()
        self.peers=private_json(self.path,{})
        self.failures={}
        self.invitation=None
    def invite(self):
        with self.lock:
            token=secrets.token_urlsafe(32)
            self.invitation=(hashlib.sha256(token.encode()).hexdigest(),time.monotonic()+180)
            return token,time.time()+180
    def pair(self,token,client_id,name,address):
        client_id=identifier(client_id); name=text(name,128)
        with self.lock:
            now=time.monotonic()
            self.peers={key:peer for key,peer in self.peers.items() if peer.get('expires_at',0)>time.time()}
            self.failures={ip:item for ip,item in self.failures.items() if now-item[1]<60}
            attempts=self.failures.get(address,(0,now))[0]
            if attempts>=5 or len(self.peers)>=32: raise PeerError('rate_limited','Pairing limit reached',429)
            self.failures[address]=(attempts+1,now)
            valid=isinstance(token,str) and len(token)<=128 and self.invitation and self.invitation[1]>now
            if not valid or not hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(),self.invitation[0]):
                raise PeerError('invalid_invitation','Invitation is invalid or expired',401)
            self.invitation=None  # Atomic single-use admission.
            self.failures.pop(address,None)
            credential=secrets.token_urlsafe(32)
            self.peers[client_id]={'name':name,'hash':hashlib.sha256(credential.encode()).hexdigest(),'expires_at':time.time()+30*86400}
            write_private(self.path,self.peers)
            return {'client_id':client_id,'token':credential,'expires_at':self.peers[client_id]['expires_at']}
    def authorize(self,token):
        if not isinstance(token,str) or len(token)>128: return False
        digest=hashlib.sha256(token.encode()).hexdigest()
        with self.lock:
            return any(p.get('expires_at',0)>time.time() and hmac.compare_digest(p.get('hash',''),digest) for p in self.peers.values())
    def revoke(self,client_id):
        with self.lock:
            self.peers.pop(identifier(client_id),None)
            write_private(self.path,self.peers)
    def listing(self):
        with self.lock:
            return [{'id':key,'name':peer['name'],'expires_at':peer['expires_at']} for key,peer in self.peers.items()]

def certificate(folder,address):
    folder=pathlib.Path(folder)
    cert,key=folder/'certificate.pem',folder/'private-key.pem'
    config=folder/'certificate.conf'
    for path in (cert,key,config):
        if path.is_symlink() or (path.exists() and (path.stat().st_uid!=os.getuid() or path.stat().st_mode & 0o077)):
            raise PeerError('unsafe_state','Certificate file has unsafe permissions')
    address_changed=config.exists() and ('subjectAltName=IP:'+address+',') not in config.read_text()
    expired=cert.exists() and subprocess.run(['/usr/bin/openssl','x509','-checkend','86400','-noout','-in',str(cert)],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode!=0
    if not cert.exists() or not key.exists() or address_changed or expired:
        config.write_text('[req]\ndistinguished_name=dn\nx509_extensions=ext\nprompt=no\n[dn]\nCN=cmux Developer Peer\n[ext]\nsubjectAltName=IP:'+address+',IP:127.0.0.1,DNS:localhost\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n')
        os.chmod(config,0o600)
        subprocess.run(['/usr/bin/openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','365','-config',str(config),'-keyout',str(key),'-out',str(cert)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        os.chmod(key,0o600); os.chmod(cert,0o600)
    for path in (cert,key):
        if path.is_symlink() or path.stat().st_uid!=os.getuid() or path.stat().st_mode & 0o077:
            raise PeerError('unsafe_state','Certificate file has unsafe permissions')
    return cert,key

class PeerServer(BoundedServerMixin,http.server.ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=False
    def __init__(self,bind,context,broker,grants,host_id,name,internet=False):
        self.context=context; self.broker=broker; self.grants=grants; self.host_id=host_id; self.name=name; self.internet=internet
        self.configure_connection_limits(tls_context=context)
        super().__init__(bind,Handler)
    def connection_allowed(self,address): return private_address(address[0],self.internet)

class Handler(BoundedRequestMixin,http.server.BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    server_version='cmux-peer'
    sys_version=''
    def log_message(self,*args): pass
    def answer(self,status,value):
        payload=json.dumps(value,separators=(',',':')).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(payload)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        keep=bool(getattr(self,'admitted',False)) and status==200 and self.request_version=='HTTP/1.1' and self.headers.get('Connection','').lower()!='close'
        self.send_header('Connection','keep-alive' if keep else 'close')
        self.end_headers(); self.wfile.write(payload); self.close_connection=not keep
    def body(self):
        if self.headers.get('Content-Type','').split(';')[0]!='application/json': raise PeerError('invalid_content_type','JSON required',415)
        try: length=int(self.headers.get('Content-Length','0'))
        except ValueError: raise PeerError('invalid_body','Invalid body')
        if not 0<length<=MAX_BODY or self.headers.get('Transfer-Encoding'): raise PeerError('invalid_body','Body limit exceeded',413)
        try: return strict_json(self.rfile.read(length))
        except (ValueError,UnicodeError): raise PeerError('invalid_body','Malformed JSON')
    def auth(self):
        if self.headers.get('Origin') is not None: raise PeerError('browser_denied','Use the paired desktop app',403)
        auth=self.headers.get('Authorization','')
        if not auth.startswith('Bearer ') or not self.server.grants.authorize(auth[7:]):
            raise PeerError('unauthorized','Pair this computer first',401)
        self.admitted=True
        self.token=auth[7:]
    def admit_mutation(self):
        if self.request_expired or not self.server.grants.authorize(self.token):
            raise PeerError('access_revoked','Access was revoked or the request expired',403)
    def do_GET(self):
        self.handle_api(False)
    def do_POST(self):
        self.handle_api(True)
    def handle_api(self,post):
        self.admitted=False
        try:
            if post and self.path=='/v1/pair':
                if self.headers.get('Origin') is not None: raise PeerError('browser_denied','Desktop pairing required',403)
                body=self.body(); fields(body,{'invitation','client_id','name'})
                result=self.server.grants.pair(body.get('invitation'),body.get('client_id'),body.get('name'),self.client_address[0])
                result.update(host_id=self.server.host_id,host_name=self.server.name,protocol=1)
            else:
                self.auth()
                if not post and self.path=='/v1/catalog':
                    result=dict(self.server.broker.catalog(),host_id=self.server.host_id,host_name=self.server.name,protocol=1)
                elif post and self.path=='/v1/replay': result=self.server.broker.replay(self.body())
                elif post and self.path=='/v1/input': result=self.server.broker.input(self.body(),admission=self.admit_mutation)
                elif post and self.path=='/v1/files': result=self.server.broker.files(self.body())
                elif post and self.path=='/v1/action': result=self.server.broker.action(self.body(),admission=self.admit_mutation)
                else: raise PeerError('unknown_route','This action is not exported',404)
            self.answer(200,{'ok':True,'result':result})
        except PeerError as error: self.answer(error.status,{'ok':False,'error':{'code':error.code,'message':str(error)}})
        except Exception: self.answer(503,{'ok':False,'error':{'code':'owner_unavailable','message':'The source app is unavailable; no action was redirected.'}})

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--socket',required=True)
    parser.add_argument('--bind',required=True)
    parser.add_argument('--port',type=int,default=0)
    parser.add_argument('--state-dir',required=True)
    parser.add_argument('--name',default=socket.gethostname())
    parser.add_argument('--internet',action='store_true')
    args=parser.parse_args()
    if not private_address(args.bind,args.internet) or not 0<=args.port<=65535: parser.error('Only a specific private/loopback address is permitted')
    grants=Grants(args.state_dir)
    identity_path=grants.folder/'identity.json'
    identity=private_json(identity_path,{'host_id':str(uuid.uuid4())})
    write_private(identity_path,identity)
    cert,key=certificate(grants.folder,args.bind)
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.minimum_version=ssl.TLSVersion.TLSv1_2
    context.options|=ssl.OP_NO_COMPRESSION
    context.load_cert_chain(cert,key)
    broker=OwnerBroker(args.socket)
    server=PeerServer((args.bind,args.port),context,broker,grants,identity['host_id'],args.name,args.internet)
    endpoint='https://'+args.bind+':'+str(server.server_port)
    der=ssl.PEM_cert_to_DER_cert(cert.read_text())
    def announce():
        secret,expiry=grants.invite()
        invitation={'protocol':1,'endpoint':endpoint,'host_id':identity['host_id'],'host_name':args.name,'certificate_der':base64.b64encode(der).decode(),'invitation':secret,'expires_at':expiry}
        encoded='cmux-peer-v1:'+base64.urlsafe_b64encode(json.dumps(invitation,separators=(',',':')).encode()).decode()
        print(json.dumps({'event':'invitation','invitation':encoded,'endpoint':endpoint,'expires_at':expiry}),flush=True)
    def commands():
        for line in sys.stdin:
            try:
                request=json.loads(line)
                if request.get('command')=='invite': announce()
                elif request.get('command')=='peers': print(json.dumps({'event':'peers','peers':grants.listing()}),flush=True)
                elif request.get('command')=='revoke': grants.revoke(request['client_id']); print(json.dumps({'event':'revoked','client_id':request['client_id']}),flush=True)
                elif request.get('command')=='stop': server.shutdown(); return
            except Exception: print(json.dumps({'event':'command_error'}),flush=True)
        server.shutdown()  # App died or intentionally closed its control pipe.
    threading.Thread(target=commands,daemon=True).start()
    def stop(*_): threading.Thread(target=server.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,stop); signal.signal(signal.SIGINT,stop)
    announce()
    try: server.serve_forever(poll_interval=0.25)
    finally: server.server_close()

if __name__=='__main__': main()
