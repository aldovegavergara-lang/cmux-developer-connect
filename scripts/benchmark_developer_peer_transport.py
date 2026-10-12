#!/usr/bin/env python3
"""Measure the real Swift TLS/JSON client, with no native app or live terminal."""
import argparse,base64,importlib.util,json,pathlib,ssl,subprocess,tempfile,threading,uuid
root=pathlib.Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--output',type=pathlib.Path,required=True);args=parser.parse_args()
spec=importlib.util.spec_from_file_location('peer_benchmark',root/'Resources/bin/cmux-peer-service.py')
peer=importlib.util.module_from_spec(spec);spec.loader.exec_module(peer)
class Broker:
 def catalog(self):return {'padding':'x'*65536}
with tempfile.TemporaryDirectory(prefix='cmux-peer-benchmark-') as directory:
 folder=pathlib.Path(directory).resolve();grants=peer.Grants(str(folder/'host'))
 cert,key=peer.certificate(str(folder/'host'),'127.0.0.1');context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert,key)
 server=peer.PeerServer(('127.0.0.1',0),context,Broker(),grants,str(uuid.uuid4()),'Benchmark')
 worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
 invitation,_=grants.invite();credential=grants.pair(invitation,str(uuid.uuid4()),'native','127.0.0.1')
 fixture=folder/'fixture.json';fixture.write_text(json.dumps(dict(credential,endpoint='https://127.0.0.1:'+str(server.server_port),certificate=base64.b64encode(ssl.PEM_cert_to_DER_cert(cert.read_text())).decode())));fixture.chmod(0o600)
 code=folder/'Main.swift';code.write_text('''import Foundation
import Darwin
@main enum PeerBenchmark {
 static func cpu() -> Double {
  var r = rusage(); getrusage(RUSAGE_SELF, &r)
  return Double(r.ru_utime.tv_sec+r.ru_stime.tv_sec)+Double(r.ru_utime.tv_usec+r.ru_stime.tv_usec)/1_000_000
 }
 static func main() async throws {
  let o = try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))) as! [String: Any]
  let client = LocalPeerClient(LocalPeerCredential(hostID: UUID().uuidString, hostName: "Benchmark", endpoint: URL(string:o["endpoint"] as! String)!, certificate:Data(base64Encoded:o["certificate"] as! String)!, clientID:o["client_id"] as! String, token:o["token"] as! String, expiresAt:Date().addingTimeInterval(300)))
  _ = try await client.request("/v1/catalog")
  let start = ProcessInfo.processInfo.systemUptime, before = cpu()
  for _ in 0..<20 {
   let data = try await client.request("/v1/catalog")
   let result = try JSONSerialization.jsonObject(with:data) as! [String:Any]
   precondition((result["padding"] as! String).utf8.count == 65536)
  }
  let result:[String:Any] = ["requests":20,"payload_bytes":65536,"wall_seconds":ProcessInfo.processInfo.systemUptime-start,"cpu_seconds":cpu()-before,"scope":"Swift TLS and JSON client, warm persistent connection; not whole app CPU"]
  print(String(data:try JSONSerialization.data(withJSONObject:result),encoding:.utf8)!)
 }
}
''')
 try:
  files=['LocalPeerClient.swift','LocalPeerCredential.swift','LocalPeerError.swift','LocalPeerPinnedSessionDelegate.swift']
  subprocess.run(['xcrun','swiftc','-swift-version','6','-O','-o',str(folder/'benchmark')]+[str(root/'Sources/LocalPeers'/f) for f in files]+[str(code)],check=True)
  result=subprocess.check_output([str(folder/'benchmark'),str(fixture)],text=True,timeout=45)
  args.output.write_text(json.dumps(json.loads(result),indent=2)+'\n');print(result.strip())
 finally:server.shutdown();server.server_close();worker.join()
