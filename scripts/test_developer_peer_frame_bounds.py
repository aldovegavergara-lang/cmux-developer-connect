#!/usr/bin/env python3
"""Execute the product's peer decoder and real shared frame DTO, without rendering hostile grids."""
import argparse,pathlib,subprocess,tempfile
root=pathlib.Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--benchmark',action='store_true');parser.add_argument('--source-ref');args=parser.parse_args()
source=subprocess.check_output(['git','-C',str(root),'show',args.source_ref+':Sources/LocalPeers/LocalPeerMirror.swift'],text=True) if args.source_ref else (root/'Sources/LocalPeers/LocalPeerMirror.swift').read_text()
start=source.index('    #if compiler(>=6.2)',source.index('final class LocalPeerMirror'))
end=source.index('    func stop()',start)
decoder=source[start:end].replace('nonisolated private static func','nonisolated static func')
with tempfile.TemporaryDirectory(prefix='cmux-peer-frame-bounds-') as temporary:
 folder=pathlib.Path(temporary)
 extracted=folder/'Decoder.swift';extracted.write_text('import Foundation\nenum FrameBoundary {\n'+decoder+'\n}\n')
 main=folder/'Main.swift';main.write_text('''import Foundation
import Darwin
@main enum FrameBoundsTest {
 static func cpu() -> Double {
  var r=rusage();getrusage(RUSAGE_SELF,&r)
  return Double(r.ru_utime.tv_sec+r.ru_stime.tv_sec)+Double(r.ru_utime.tv_usec+r.ru_stime.tv_usec)/1_000_000
 }
 static func main() async throws {
  if CommandLine.arguments.contains("--benchmark") {
   var spans:[MobileTerminalRenderGridFrame.RowSpan] = []
   for row in 0..<60 {for group in 0..<12 {spans.append(.init(row:row,column:group*16,styleID:0,text:"abcdefghijklmnop"))}}
   let example=try MobileTerminalRenderGridFrame(surfaceID:UUID().uuidString,stateSeq:1,columns:200,rows:60,rowSpans:spans)
   let bytes=try JSONSerialization.data(withJSONObject:["render_grid":example.jsonObject()])
   _ = try await FrameBoundary.decode(bytes)
   let start=ProcessInfo.processInfo.systemUptime,before=cpu()
   for _ in 0..<200 {let frame=try await FrameBoundary.decode(bytes);precondition(frame.rowSpans.count==720)}
   let result:[String:Any] = ["frames":200,"payload_bytes":bytes.count,"cpu_seconds":cpu()-before,"wall_seconds":ProcessInfo.processInfo.systemUptime-start,"scope":"real peer decoder and shared DTO, optimized Swift; no GPU or app rendering"]
   print(String(data:try JSONSerialization.data(withJSONObject:result),encoding:.utf8)!);return
  }
  let safe = try MobileTerminalRenderGridFrame(surfaceID:UUID().uuidString,stateSeq:1,columns:80,rows:24,rowSpans:[])
  let object = try safe.jsonObject()
  func payload(_ grid:[String:Any]) throws -> Data {try JSONSerialization.data(withJSONObject:["render_grid":grid])}
  _ = try await FrameBoundary.decode(payload(object))
  var overflow=object
  overflow["row_spans"]=[["row":0,"column":1,"style_id":0,"text":"x","cell_width":Int.max]]
  do {
   _ = try await FrameBoundary.decode(payload(overflow))
   FileHandle.standardError.write(Data("FAIL: overflow cell width accepted\\n".utf8));exit(1)
  } catch {}
  var violations:[String] = []
  for (key,value) in [("columns",1_000_000),("rows",1_000_000),("scrollback_rows",1_000_000),("scrolled_rows",1_000_000)] {
   var malformed=object;malformed[key]=value
   do { _ = try await FrameBoundary.decode(payload(malformed));violations.append(key) } catch {}
  }
  guard violations.isEmpty else {
   FileHandle.standardError.write(Data("FAIL: unbounded remote frame fields accepted: \\(violations.joined(separator:", "))\\n".utf8));exit(1)
  }
  let printable = try MobileTerminalRenderGridFrame(surfaceID:UUID().uuidString,stateSeq:1,columns:80,rows:24,rowSpans:[.init(row:0,column:0,styleID:0,text:"\\u{1b}]52;c;QUJD\\u{7}")])
  let frame = try await FrameBoundary.decode(payload(printable.jsonObject()))
  let bytes = MobileTerminalRenderGridReplay(frame).patchBytes()
  precondition(!String(decoding:bytes,as:UTF8.self).contains("\\u{1b}]52;"),"Untrusted clipboard escape emitted")
  print("PASS: bounded peer geometry/history and printable VT replay, using real shared DTO")
 }
}
''')
 core=root/'Packages/Shared/CMUXMobileCore/Sources/CMUXMobileCore'
 files=[core/'MobileTerminalRenderGrid.swift',core/'MobileTerminalRenderGridReplay.swift',core/'MobileTerminalHostTiming.swift',core/'MobileTerminalRenderGridStyle+ColorSource.swift',core/'TerminalTheme.swift',core/'CellRelativeColor.swift']
 files+=[f for f in sorted(core.glob('MobileTerminalRenderGridFrame+*.swift')) if not f.name.endswith('+Emission.swift')]+sorted(core.glob('MobileTerminalRenderGridReplay+*.swift'))
 subprocess.run(['xcrun','swiftc','-swift-version','6']+(['-O'] if args.benchmark else [])+['-o',str(folder/'test')]+[str(f) for f in files]+[str(root/'Sources/LocalPeers/LocalPeerError.swift'),str(extracted),str(main)],check=True)
 subprocess.run([str(folder/'test')]+(['--benchmark'] if args.benchmark else []),check=True,timeout=30)
