#!/usr/bin/env python3
"""Exercise the native tree's real node sorting in a small standalone Swift harness."""
import pathlib
import subprocess
import tempfile

repo = pathlib.Path(__file__).resolve().parents[1]
source = (repo / 'Sources/FileExplorerStore.swift').read_text()
node = source.split('final class FileExplorerNode: Identifiable {', 1)[1].split('// MARK: - Root Resolver', 1)[0]
view_source = (repo / 'Sources/FileExplorerView.swift').read_text()
refresh = view_source.split('        private func refreshLoadedNodes(in outlineView: NSOutlineView) {', 1)[1].split('        // MARK: - NSOutlineViewDataSource', 1)[0]
should_expand = view_source.split('        func outlineView(_ outlineView: NSOutlineView, shouldExpandItem item: Any) -> Bool {', 1)[1].split('        func outlineView(_ outlineView: NSOutlineView, shouldCollapseItem', 1)[0]
refresh_wrapper = '''
final class NSOutlineView {
    let nodes: [FileExplorerNode]
    var numberOfRows: Int { nodes.count }
    var expanded: Set<String> = []
    var reloads = 0
    init(_ nodes: [FileExplorerNode]) { self.nodes = nodes }
    func item(atRow row: Int) -> Any? { row < nodes.count ? nodes[row] : nil }
    func isItemExpanded(_ node: FileExplorerNode) -> Bool { expanded.contains(node.path) }
    func reloadItem(_ node: FileExplorerNode, reloadChildren: Bool) { reloads += 1 }
    func expandItem(_ node: FileExplorerNode) { expanded.insert(node.path) }
    func collapseItem(_ node: FileExplorerNode) { expanded.remove(node.path) }
}
final class Store {
 var expandedPaths: Set<String> = []
 var expansionRequests = 0
 func expand(node: FileExplorerNode) { expansionRequests += 1; expandedPaths.insert(node.path) }
 func isExpanded(_ node: FileExplorerNode) -> Bool { expandedPaths.contains(node.path) }
}
final class Coordinator {
    let store = Store()
    var lastLoadedChildrenRevisions: [ObjectIdentifier: UInt64] = [:]
    func refreshLoadedNodes(in outlineView: NSOutlineView) {
''' + refresh + '''
 var isUpdatingOutlineProgrammatically = false
 func outlineView(_ outlineView: NSOutlineView, shouldExpandItem item: Any) -> Bool {
''' + should_expand + '}\n'
harness = '''
let root = FileExplorerNode(name: "root", path: "/root", isDirectory: true)
root.children = (0..<4000).reversed().map {
    FileExplorerNode(name: String(format: "entry%05d", $0), path: "/root/\\($0)", isDirectory: $0 % 2 == 0)
}
let first = root.sortedChildren!
precondition(first.count == 4000 && first.first!.name == "entry00000")
precondition(first[1999].isDirectory && !first[2000].isDirectory)
let began = Date()
for _ in 0..<100 { precondition(root.sortedChildren!.count == 4000) }
let elapsed = Date().timeIntervalSince(began)
print("100 reads of a 4000-entry directory: \\(elapsed) seconds")
precondition(elapsed < 0.5, "tree repeats expensive sorting during row reads")
let inserted = FileExplorerNode(name: "AAA", path: "/root/new", isDirectory: true)
root.children!.append(inserted)
precondition(root.sortedChildren!.first === inserted)
root.children = nil
precondition(root.sortedChildren == nil)
root.children = []
precondition(root.sortedChildren!.isEmpty)
print("PASS: folders first, stable ordering, mutations and empty directories")
let directory = FileExplorerNode(name: "src", path: "/src", isDirectory: true)
directory.children = [inserted]
let outline = NSOutlineView([directory])
outline.expanded = [directory.path]
let coordinator = Coordinator()
coordinator.store.expandedPaths = [directory.path]
coordinator.refreshLoadedNodes(in: outline)
let firstReloads = outline.reloads
coordinator.refreshLoadedNodes(in: outline)
guard outline.reloads == firstReloads else {
    FileHandle.standardError.write(Data("FAIL: unchanged rows reload their children on every update\\n".utf8))
    exit(1)
}
directory.children = []
coordinator.refreshLoadedNodes(in: outline)
precondition(outline.reloads == firstReloads + 1)
print("PASS: unchanged tree stays idle; changed directory refreshes")
let closed = FileExplorerNode(name: "private", path: "/private-folder", isDirectory: true)
closed.children = []
coordinator.isUpdatingOutlineProgrammatically = true
let probes = coordinator.store.expansionRequests
if coordinator.outlineView(outline, shouldExpandItem: closed) || coordinator.store.expansionRequests != probes {
 FileHandle.standardError.write(Data("FAIL: a programmatic outline reload opens an unrequested directory\\n".utf8))
 exit(1)
}
coordinator.isUpdatingOutlineProgrammatically = false
precondition(coordinator.outlineView(outline, shouldExpandItem: closed))
precondition(coordinator.store.expansionRequests == probes + 1)
print("PASS: programmatic probes do not open folders; an explicit expansion still works")
'''
with tempfile.TemporaryDirectory(prefix='cmux-tree-check-') as temporary:
    folder = pathlib.Path(temporary)
    swift = folder / 'main.swift'
    swift.write_text('import Foundation\nfinal class FileExplorerNode: Identifiable {' + node + refresh_wrapper + harness)
    subprocess.run(['xcrun', 'swiftc', '-O', str(swift), '-o', str(folder / 'test')], check=True)
    result = subprocess.run([str(folder / 'test')], capture_output=True, text=True)
    print(result.stdout, end='')
    print(result.stderr, end='')
    if result.returncode:
        print('FAIL: native tree performance/behavior regression')
        raise SystemExit(1)
