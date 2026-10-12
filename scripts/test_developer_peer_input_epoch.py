#!/usr/bin/env python3
"""Execute the real chunk sender while the producer changes after its first write."""
import pathlib,subprocess,tempfile
root=pathlib.Path(__file__).resolve().parents[1]
source=(root/'Sources/LocalPeers/LocalPeerMirror.swift').read_text()
epoch=source[source.index('private final class LocalPeerInputEpoch'):source.index('/// One native Ghostty view')]
sender=source.split('input = DeviceTerminalInputRouter(send: { data in',1)[1].split('}, onFailure:',1)[0]
with tempfile.TemporaryDirectory(prefix='cmux-peer-input-epoch-') as temporary:
 folder=pathlib.Path(temporary);code=folder/'Main.swift'
 code.write_text('''import Foundation
'''+epoch+'''
private actor FixtureClient {
 let epoch:LocalPeerInputEpoch
 var values:[String] = []
 init(_ epoch:LocalPeerInputEpoch) {self.epoch=epoch}
 func request(_ path:String,body:Data) async throws -> Data {
  let object=try JSONSerialization.jsonObject(with:body) as! [String:Any]
  values.append(object["expected_render_epoch"] as! String)
  if values.count==1 {epoch.set("replacement-producer")}
  return Data()
 }
}
enum LocalPeerError:Error {case malformed,disconnected}
@main enum EpochTest {
 static func main() async throws {
  let epoch=LocalPeerInputEpoch();epoch.set("original-producer")
  let client=FixtureClient(epoch),workspaceID=UUID().uuidString,surfaceID=UUID().uuidString
  let send: (Data) async throws -> Void = {data in
'''+sender+'''
  }
  try await send(Data(String(repeating:"x",count:17000).utf8))
  let values=await client.values
  guard values.count==3 && values.allSatisfy({$0=="original-producer"}) else {
   FileHandle.standardError.write(Data("FAIL: one paste crossed into a replacement producer\\n".utf8));exit(1)
  }
  print("PASS: all chunks of one paste retain their original producer epoch")
 }
}
''')
 subprocess.run(['xcrun','swiftc','-parse-as-library','-swift-version','6',str(code),'-o',str(folder/'test')],check=True)
 subprocess.run([str(folder/'test')],check=True)
