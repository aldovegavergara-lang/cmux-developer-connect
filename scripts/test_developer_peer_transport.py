#!/usr/bin/env python3
"""Compile the real Swift transport and exercise it against a real private TLS server."""
import base64
import importlib.util
import json
import http.server
import pathlib
import ssl
import subprocess
import tempfile
import threading
import uuid

root=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('peer_transport_server',root/'Resources/bin/cmux-peer-service.py')
peer=importlib.util.module_from_spec(spec); spec.loader.exec_module(peer)
class Broker:
    def catalog(self): return {'workspaces':[]}

with tempfile.TemporaryDirectory(prefix='cmux-native-peer-') as directory:
    folder=pathlib.Path(directory).resolve()
    grants=peer.Grants(str(folder/'host'))
    cert,key=peer.certificate(str(folder/'host'),'127.0.0.1')
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); context.load_cert_chain(cert,key)
    server=peer.PeerServer(('127.0.0.1',0),context,Broker(),grants,str(uuid.uuid4()),'Transport test')
    worker=threading.Thread(target=server.serve_forever,daemon=True); worker.start()
    secondary_calls=[]
    class Sink(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            secondary_calls.append(True);self.send_response(200);self.send_header('Content-Length','0');self.end_headers()
    sink=http.server.ThreadingHTTPServer(('127.0.0.1',0),Sink)
    sink.socket=context.wrap_socket(sink.socket,server_side=True)
    sink_worker=threading.Thread(target=sink.serve_forever,daemon=True);sink_worker.start()
    original_handler=server.RequestHandlerClass
    class Adversarial(original_handler):
        def do_GET(self):
            if self.path=='/v1/redirect':
                self.send_response(302);self.send_header('Location','https://127.0.0.1:'+str(sink.server_port)+'/v1/catalog');self.send_header('Content-Length','0');self.end_headers();return
            if self.path=='/v1/oversize':
                self.send_response(200);self.send_header('Content-Length',str(4*1024*1024+1));self.end_headers();self.wfile.write(b'x'*(4*1024*1024+1));return
            if self.path=='/v1/streamed-oversize':
                self.send_response(200);self.send_header('Transfer-Encoding','chunked');self.end_headers()
                try:
                    prefix=b'{"ok":true,"result":{"padding":"'
                    self.wfile.write(format(len(prefix),'x').encode()+b'\r\n'+prefix+b'\r\n')
                    for _ in range(65):
                        self.wfile.write(b'10000\r\n'+b'x'*65536+b'\r\n')
                    self.wfile.write(b'3\r\n"}}\r\n')
                    self.wfile.write(b'0\r\n\r\n')
                except OSError:pass
                return
            super().do_GET()
    server.RequestHandlerClass=Adversarial
    invitation,_=grants.invite()
    credential=grants.pair(invitation,str(uuid.uuid4()),'native','127.0.0.1')
    fixture=folder/'fixture.json'
    fixture.write_text(json.dumps(dict(credential,endpoint='https://127.0.0.1:'+str(server.server_port),
        certificate=base64.b64encode(ssl.PEM_cert_to_DER_cert(cert.read_text())).decode())))
    fixture.chmod(0o600)
    main=folder/'Main.swift'
    main.write_text('''import Foundation
import Security
@main enum PeerTransportTest {
    static func main() async throws {
        let object = try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))) as! [String: Any]
        let cert = Data(base64Encoded: object["certificate"] as! String)!
        let leaf = SecCertificateCreateWithData(nil, cert as CFData)!
        var trust: SecTrust?
        SecTrustCreateWithCertificates(leaf, SecPolicyCreateSSL(true, "127.0.0.1" as CFString), &trust)
        SecTrustSetAnchorCertificates(trust!, [leaf] as CFArray)
        SecTrustSetAnchorCertificatesOnly(trust!, true)
        var failure: CFError?
        guard SecTrustEvaluateWithError(trust!, &failure) else { fatalError("Certificate anchor validation failed") }
        let endpoint = URL(string: object["endpoint"] as! String)!
        func client(_ certificate: Data, _ token: String) -> LocalPeerClient {
            LocalPeerClient(LocalPeerCredential(hostID: UUID().uuidString, hostName: "Test", endpoint: endpoint,
                certificate: certificate, clientID: object["client_id"] as! String, token: token,
                expiresAt: Date().addingTimeInterval(300)))
        }
        let result = try await client(cert, object["token"] as! String).request("/v1/catalog")
        guard (try JSONSerialization.jsonObject(with: result) as? [String: Any])?["host_name"] as? String == "Transport test" else { fatalError("Invalid catalog") }
        do { _ = try await client(Data(repeating: 0, count: cert.count), object["token"] as! String).request("/v1/catalog"); fatalError("Wrong pin admitted") }
        catch { print("Wrong TLS pin rejected") }
        do { _ = try await client(cert, "wrong").request("/v1/catalog"); fatalError("Wrong credential admitted") }
        catch { print("Wrong credential rejected") }
        do { _ = try await client(cert, object["token"] as! String).request("/v1/redirect");fatalError("Redirect admitted") }
        catch LocalPeerError.disconnected {print("Redirect rejected")}
        for route in ["/v1/oversize", "/v1/streamed-oversize"] {
            do { _ = try await client(cert, object["token"] as! String).request(route);fatalError("Oversized response admitted") }
            catch LocalPeerError.malformed {print("Oversized response rejected: \\(route)")}
        }
        for address in ["127.x.0.0.1", "127..0.1", "8.8.8.8", "example.com", "0.0.0.0"] {
            guard !LocalPeerInvitation.isPrivateAddress(address) else { fatalError("Bad endpoint admitted") }
        }
        print("Native HTTPS, certificate pin, authentication and endpoint validation passed")
    }
}
''')
    files=['LocalPeerClient.swift' ,'LocalPeerCredential.swift','LocalPeerError.swift','LocalPeerPinnedSessionDelegate.swift']
    try:
        subprocess.run(['/usr/bin/xcrun','swiftc','-O','-swift-version','6','-o',str(folder/'test')]+
            [str(root/'Sources/LocalPeers'/file) for file in files]+[str(main)],check=True)
        subprocess.run([str(folder/'test'),str(fixture)],check=True,timeout=30)
        assert not secondary_calls,'Redirect forwarded a credential to the secondary endpoint'
        print('Redirect sink received no request or credential')
    finally:
        server.shutdown(); server.server_close(); worker.join()
        sink.shutdown();sink.server_close();sink_worker.join()
