#!/usr/bin/env python3
"""Real blocking filesystem reads must not exhaust Swift's networking executor."""
import os
import pathlib
import subprocess
import tempfile

root=pathlib.Path(__file__).resolve().parents[1]
source=(root/'Sources/FileExplorerStore.swift').read_text()
def declaration(marker):
    start=source.index(marker); opening=source.index('{',start); depth=1; index=opening+1
    while depth:
        if source[index]=='{': depth+=1
        elif source[index]=='}': depth-=1
        index+=1
    return source[start:index]

with tempfile.TemporaryDirectory(prefix='cmux-explorer-io-') as directory:
    folder=pathlib.Path(directory)
    # Foundation waits opening these like a slow/unavailable filesystem.
    for n in range((os.cpu_count() or 8)+8): os.mkfifo(folder/str(n))
    main=folder/'Main.swift'
    main.write_text('import Foundation\nimport Darwin\n'+declaration('struct FileExplorerEntry: Sendable')+'\n'+
        declaration('protocol FileExplorerProvider: AnyObject')+'\n'+declaration('final class LocalFileExplorerProvider: FileExplorerProvider')+'''
@main enum FilesystemIsolationTest {
    static func main() {
        let paths = Array(CommandLine.arguments.dropFirst())
        for path in paths {
            Task.detached(priority: .userInitiated) {
                // A real open(2) waits on the FIFO, just like the observed stalled filesystem reads.
                let provider = LocalFileExplorerProvider(read: { path, _ in
                    let fd = Darwin.open(path, O_RDONLY)
                    if fd >= 0 { Darwin.close(fd) }
                    return []
                })
                _ = try? await provider.listDirectory(path: path, showHidden: true)
            }
        }
        DispatchQueue.global().asyncAfter(deadline: .now() + 0.2) {
            Task.detached(priority: .userInitiated) {
                print("PASS: async control and network tasks remain runnable during stalled filesystem reads")
                exit(0)
            }
        }
        DispatchQueue.global().asyncAfter(deadline: .now() + 2) {
            FileHandle.standardError.write(Data("FAIL: filesystem reads starved the Swift executor\\n".utf8))
            exit(1)
        }
        dispatchMain()
    }
}
''')
    subprocess.run(['/usr/bin/xcrun','swiftc','-parse-as-library','-swift-version','6',str(main),'-o',str(folder/'test')],check=True)
    try:
        result=subprocess.run([str(folder/'test')]+[str(folder/str(n)) for n in range((os.cpu_count() or 8)+8)],
        capture_output=True,text=True,timeout=5)
    except subprocess.TimeoutExpired:
        print('FAIL: stalled filesystem reads prevented async control tasks from running within five seconds')
        raise SystemExit(1)
    print(result.stdout,end=''); print(result.stderr,end='')
    raise SystemExit(result.returncode)
