import Foundation

/// App-only ownership marker; secrets live in Keychain, never workspace snapshots.
@MainActor
final class LocalPeerWorkspaceBinding {
    let client: LocalPeerClient
    let remoteWorkspaceID: String
    var mirrors: [String: LocalPeerMirror] = [:]
    private var lastSurfaceID: String?
    init(client: LocalPeerClient, workspaceID: String) {
        self.client = client; remoteWorkspaceID = workspaceID
    }
    func fileRoot(for workspace: Workspace) -> LocalPeerFileRoot? {
        let focused = mirrors.values.first(where: { $0.panel?.id == workspace.focusedPanelId })
        if let focused { lastSurfaceID = focused.remoteSurfaceID }
        guard let mirror = focused ?? lastSurfaceID.flatMap({ mirrors[$0] }) ?? mirrors.keys.sorted().first.flatMap({ mirrors[$0] }),
              !mirror.directory.isEmpty else { return nil }
        return LocalPeerFileRoot(workspaceID: workspace.id, remoteWorkspaceID: remoteWorkspaceID,
            remoteSurfaceID: mirror.remoteSurfaceID, path: mirror.directory, client: client)
    }
    func stop() { mirrors.values.forEach { $0.stop() }; mirrors.removeAll() }
}
