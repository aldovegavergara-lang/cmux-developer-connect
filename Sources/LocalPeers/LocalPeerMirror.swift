import CMUXMobileCore
import CmuxTerminal
import Foundation
import Combine

private final class LocalPeerInputEpoch: @unchecked Sendable {
    private let lock = NSLock()
    private var value: String?
    private var lastInput: TimeInterval = -.infinity
    func noteInput() { lock.lock(); lastInput = ProcessInfo.processInfo.systemUptime; lock.unlock() }
    func hasRecentInput() -> Bool {
        lock.lock(); defer { lock.unlock() }
        return ProcessInfo.processInfo.systemUptime - lastInput < 2
    }
    func set(_ value: String?) { lock.lock(); self.value = value; lock.unlock() }
    func get() throws -> String {
        lock.lock(); defer { lock.unlock() }
        guard let value, !value.isEmpty else { throw LocalPeerError.disconnected }
        return value
    }
}

/// One native Ghostty view of the original Mac's existing PTY. No local shell.
@MainActor
final class LocalPeerMirror: ObservableObject {
    let client: LocalPeerClient
    let remoteWorkspaceID: String
    let remoteSurfaceID: String
    weak var workspace: Workspace?
    weak var panel: TerminalPanel?
    var directory: String
    private var task: Task<Void, Never>?
    private var lastFrame: MobileTerminalRenderGridFrame?
    private var lastVisibleChange: TimeInterval = -.infinity
    @Published private(set) var connected = false
    @Published private(set) var hasConnected = false
    private var input: DeviceTerminalInputRouter!
    private let epoch = LocalPeerInputEpoch()

    init(client: LocalPeerClient, workspaceID: String, surfaceID: String, directory: String) {
        self.client = client; remoteWorkspaceID = workspaceID; remoteSurfaceID = surfaceID; self.directory = directory
        let epoch = self.epoch
        input = DeviceTerminalInputRouter(send: { data in
            guard let value = String(data: data, encoding: .utf8) else { throw LocalPeerError.malformed }
            let renderEpoch = try epoch.get()
            // Chunk at Unicode scalar boundaries. A large paste keeps its byte order.
            var chunk = ""
            var size = 0
            for scalar in value.unicodeScalars {
                let count = String(scalar).utf8.count
                if size + count > 8192 {
                    let body = try JSONSerialization.data(withJSONObject: ["workspace_id": workspaceID,
                        "surface_id": surfaceID, "text": chunk, "expected_render_epoch": renderEpoch])
                    _ = try await client.request("/v1/input", body: body)
                    chunk = ""; size = 0
                }
                chunk.unicodeScalars.append(scalar); size += count
            }
            if !chunk.isEmpty {
                let body = try JSONSerialization.data(withJSONObject: ["workspace_id": workspaceID,
                    "surface_id": surfaceID, "text": chunk, "expected_render_epoch": renderEpoch])
                _ = try await client.request("/v1/input", body: body)
            }
        }, onFailure: { [weak self] _ in
            Task { @MainActor [weak self] in
                self?.epoch.set(nil)
                if self?.connected == true { self?.connected = false }
                self?.input?.setEnabled(false)
            }
        })
    }
    func mount(in workspace: Workspace, title: String) -> TerminalPanel? {
        self.workspace = workspace
        guard let input else { return nil }
        guard let panel = workspace.addRemoteTmuxDisplayPane(remotePaneId: 0, title: title,
            focus: false, onInput: { [input, epoch] in epoch.noteInput(); input.enqueue($0) }) else { return nil }
        self.panel = panel
        task = Task { [weak self] in
            while !Task.isCancelled {
                guard let self, let workspace = self.workspace, let panel = self.panel,
                      !workspace.isRetiredFromOwningTabManager, workspace.panels[panel.id] != nil else { return }
                // Hidden workspaces do not need screen captures. Their PTYs keep
                // running on the owner and the lightweight catalog tracks them.
                let visiblePane = workspace.bonsplitController.allPaneIds.contains {
                    workspace.bonsplitController.selectedTab(inPane: $0).map(\.id)
                        .flatMap(workspace.panelIdFromSurfaceId) == panel.id
                }
                guard workspace.owningTabManager?.selectedTabId == workspace.id, visiblePane else {
                    try? await Task.sleep(nanoseconds: 500_000_000)
                    continue
                }
                do {
                    let body = try JSONSerialization.data(withJSONObject: ["workspace_id": self.remoteWorkspaceID,
                        "surface_id": self.remoteSurfaceID])
                    let data = try await self.client.request("/v1/replay", body: body)
                    var frame = try await Self.decode(data)
                    guard !Task.isCancelled, frame.surfaceID.uppercased() == self.remoteSurfaceID.uppercased() else { throw LocalPeerError.malformed }
                    // Capture revisions advance even without visible changes. Compare actual content.
                    frame.renderRevision = 0; frame.stateSeq = 0
                    frame.hostTiming = nil; frame.appliedInputSequence = nil
                    if frame != self.lastFrame {
                        if self.lastFrame?.renderEpoch != frame.renderEpoch {
                            self.input.setEnabled(false) // Drop input from a replaced producer.
                        }
                        panel.surface.setAssignedGrid(columns: frame.columns, rows: frame.rows)
                        panel.surface.processRemoteOutput(MobileTerminalRenderGridReplay(frame).patchBytes())
                        self.lastFrame = frame
                        self.lastVisibleChange = ProcessInfo.processInfo.systemUptime
                    }
                    self.epoch.set(frame.renderEpoch)
                    if !self.hasConnected { self.hasConnected = true }
                    if !self.connected { self.connected = true }
                    self.input.setEnabled(true)
                } catch {
                    if self.connected { self.connected = false }
                    self.epoch.set(nil); self.input.setEnabled(false)
                }
                let selected = workspace.owningTabManager?.selectedTabId == workspace.id &&
                    AppDelegate.shared?.mainWindowContainingWorkspace(workspace.id)?.isKeyWindow == true
                let busy = self.epoch.hasRecentInput() ||
                    ProcessInfo.processInfo.systemUptime - self.lastVisibleChange < 2
                try? await Task.sleep(nanoseconds: selected && busy ? 350_000_000 : 1_500_000_000)
            }
        }
        return panel
    }
    #if compiler(>=6.2)
    @concurrent
    #endif
    nonisolated private static func decode(_ data: Data) async throws -> MobileTerminalRenderGridFrame {
        struct Snapshot: Decodable {
            let frame: MobileTerminalRenderGridFrame
            enum Key: String, CodingKey { case renderGrid = "render_grid" }
            enum GridKey: String, CodingKey {
                case columns, rows, full
                case scrollbackRows = "scrollback_rows", scrolledRows = "scrolled_rows"
            }
            init(from decoder: Decoder) throws {
                let envelope = try decoder.container(keyedBy: Key.self)
                let grid = try envelope.superDecoder(forKey: .renderGrid)
                let shape = try grid.container(keyedBy: GridKey.self)
                let columns = try shape.decode(Int.self, forKey: .columns)
                let rows = try shape.decode(Int.self, forKey: .rows)
                // Validate before DTO arithmetic or any Ghostty grid allocation.
                // This private protocol requests full, screen-only snapshots.
                guard (1...1024).contains(columns), (1...512).contains(rows),
                      columns * rows <= 262144,
                      try shape.decodeIfPresent(Bool.self, forKey: .full) ?? true,
                      (try shape.decodeIfPresent(Int.self, forKey: .scrollbackRows) ?? 0) == 0,
                      (try shape.decodeIfPresent(Int.self, forKey: .scrolledRows) ?? 0) == 0
                else { throw LocalPeerError.malformed }
                frame = try MobileTerminalRenderGridFrame(from: grid)
            }
        }
        // Decode once, retaining the shared DTO's validation and VT sanitizer.
        return try JSONDecoder().decode(Snapshot.self, from: data).frame
    }
    func stop() {
        task?.cancel(); task = nil; connected = false; input.invalidate()
    }
}
