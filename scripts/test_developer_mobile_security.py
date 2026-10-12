#!/usr/bin/env python3
"""Real mobile helper/ttyd, disposable native-RPC fixture, private loopback only."""
import base64,importlib.util,json,os,pathlib,signal,socket,ssl,struct,subprocess,sys,tempfile,time,unittest,uuid
root=pathlib.Path(__file__).resolve().parents[1]
class MobileSecurity(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(prefix='cmux-mobile-audit-',dir='/tmp');folder=pathlib.Path(self.temp.name)
  fixture=folder/'Fixture.py'
  fixture.write_text('''import argparse,importlib.util,importlib.machinery,pathlib,sys,uuid
root=pathlib.Path(sys.argv[1]);state=pathlib.Path(sys.argv[2])
spec=importlib.util.spec_from_file_location('fixture_menu',root/'scripts/test_developer_mobile_menu.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
app=module.NativeAppFixture(state/'app.sock')
helper=importlib.machinery.SourceFileLoader('mobile_fixture',str(root/'Resources/bin/cmux-mobile-share')).load_module()
fake_cli=state/'fixture-cli';fake_cli.write_text('#!/usr/bin/env python3\\nimport os\\nos.execv("/bin/cat",["cat"])\\n');fake_cli.chmod(0o700)
share=helper.MobileShare(state/'private',str(fake_cli))
share.session=lambda *args:{'session_id':str(uuid.uuid4())}
args=argparse.Namespace(transport='lan',bind='127.0.0.1',port=int(sys.argv[3]),tail_port=8443,session='audit',cwd='/tmp',command=None,readonly=False,minutes=1,reuse_pairing=None,menu=True,app_socket=str(app.path),workspace=None)
try:share.serve(args)
finally:app.close()
''')
  with socket.socket() as free:free.bind(('127.0.0.1',0));port=free.getsockname()[1]
  self.process=subprocess.Popen([sys.executable,'-B',str(fixture),str(root),str(folder),str(port)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
  line=self.process.stdout.readline().strip()
  self.assertTrue(line.startswith('PAIRING_FILE='), 'Disposable mobile service did not start')
  self.details=json.loads(pathlib.Path(line.split('=',1)[1]).read_text())
  self.context=ssl.create_default_context(cafile=self.details['certificate'])
  self.port=port
 def tearDown(self):
  if self.process.poll() is None:self.process.send_signal(signal.SIGTERM)
  try:self.process.wait(8)
  except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
  if hasattr(self,'details'):
   try:os.killpg(self.details['pid'],signal.SIGTERM)
   except ProcessLookupError:pass
  self.process.stdout.close();self.process.stderr.close();self.temp.cleanup()
 def healthy_request(self):
  with socket.create_connection(('127.0.0.1',self.port),timeout=1) as tcp:
   with self.context.wrap_socket(tcp,server_hostname='127.0.0.1') as conn:
    token=base64.b64encode(('developer:'+self.details['password']).encode())
    conn.sendall(b'GET / HTTP/1.1\r\nHost: 127.0.0.1:'+str(self.port).encode()+b'\r\nAuthorization: Basic '+token+b'\r\nConnection: close\r\n\r\n')
    return conn.recv(4096)
 def test_password_not_exposed_in_ttyd_process_arguments(self):
  command=subprocess.check_output(['ps','-p',str(self.details['pid']),'-o','command='],text=True)
  if self.details['password'] in command:self.fail('Mobile password is exposed through process arguments')
 def test_incomplete_tls_does_not_block_authenticated_mobile_client(self):
  attack=socket.create_connection(('127.0.0.1',self.port),timeout=1)
  try:
   time.sleep(.1)
   self.assertTrue(self.healthy_request().startswith(b'HTTP/1.1 200'))
  finally:attack.close()
 def test_ttyd_has_no_secondary_tcp_listener(self):
  command=subprocess.check_output(['ps','-p',str(self.details['pid']),'-o','command='],text=True)
  if 'term.sock' not in command:self.fail('Backend must use a private owner-only Unix socket')
  sockets=list(pathlib.Path(self.temp.name).glob('private/share-*/term.sock'))
  self.assertEqual(len(sockets),1)
  self.assertEqual(sockets[0].stat().st_mode & 0o777,0o600)
 def test_missing_or_wrong_auth_does_not_open_terminal_proxy(self):
  for token in [b'',b'Authorization: Basic ZGV2ZWxvcGVyOndyb25n\r\n']:
   with socket.create_connection(('127.0.0.1',self.port),timeout=1) as tcp:
    with self.context.wrap_socket(tcp,server_hostname='127.0.0.1') as conn:
     conn.sendall(b'GET /terminal/ HTTP/1.1\r\nHost: localhost\r\n'+token+b'\r\n')
     self.assertTrue(conn.recv(4096).startswith(b'HTTP/1.1 401'))
 def test_authenticated_websocket_proxies_echo_and_survives_header_deadline(self):
  os.environ.setdefault('CMUX_MOBILE_TEST_CLI','/usr/bin/true')
  spec=importlib.util.spec_from_file_location('fixture_ws',root/'scripts/test_developer_mobile_share.py')
  ws=importlib.util.module_from_spec(spec);spec.loader.exec_module(ws)
  conn=ws.WebSocket(self.details,path='/terminal/ws')
  def receive():
   def exact(count):
    data=b''
    while len(data)<count:
     chunk=conn.socket.recv(count-len(data))
     if not chunk:raise AssertionError('Authenticated fixture WebSocket closed')
     data+=chunk
    return data
   head=exact(2);length=head[1]&127
   if length==126:length=struct.unpack('!H',exact(2))[0]
   elif length==127:length=struct.unpack('!Q',exact(8))[0]
   if length>1024*1024:raise AssertionError('Unbounded fixture frame')
   mask=exact(4) if head[1]&128 else None
   data=exact(length)
   return bytes(value^mask[i%4] for i,value in enumerate(data)) if mask else data
  try:
   self.assertTrue(conn.accepted)
   conn.send(b'0SAFE_WEBSOCKET_FIXTURE_OK\r')
   received=b'';deadline=time.monotonic()+3
   while time.monotonic()<deadline and b'SAFE_WEBSOCKET_FIXTURE_OK' not in received:received+=receive()
   self.assertIn(b'SAFE_WEBSOCKET_FIXTURE_OK',received)
   time.sleep(8.2)
   conn.send(b'0STILL_AUTHENTICATED_AFTER_DEADLINE\r')
   received=b'';deadline=time.monotonic()+3
   while time.monotonic()<deadline and b'STILL_AUTHENTICATED_AFTER_DEADLINE' not in received:received+=receive()
   self.assertIn(b'STILL_AUTHENTICATED_AFTER_DEADLINE',received)
  finally:conn.close()
if __name__=='__main__':unittest.main(verbosity=2)
