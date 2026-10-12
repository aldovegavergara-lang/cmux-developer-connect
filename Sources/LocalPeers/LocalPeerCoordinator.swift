import AppKit
import Foundation
import Combine

/// Composes trusted peers into the existing local workspace sidebar.
@MainActor
final class LocalPeerCoordinator: ObservableObject {
    @Published private(set) var revision = 0
    @Published private(set) var status: [String: Bool] = [:]
    private let manager: () -> TabManager?
    private(set) var clients: [String: LocalPeerClient] = [:]
    private var tasks: [String: Task<Void, Never>] = [:]
    private var workspaces: [String: [String: Workspace]] = [:]
    private var hidden: [String: Set<String>] = [:]
    var onChange: (() -> Void)?
    init(manager: @escaping () -> TabManager?) { self.manager = manager }

    func connect(_ client: LocalPeerClient) {
        let id = client.credential.hostID
        if let previous = clients[id], previous !== client { disconnect(id) }
        clients[id] = client
        hidden.removeValue(forKey: id)
        tasks[id]?.cancel()
        tasks[id] = Task { [weak self] in
            while !Task.isCancelled {
                guard let self else { return }
                do { try await self.refresh(client); self.status[id] = true }
                catch {
                    guard !Task.isCancelled, self.clients[id] === client else { return }
                    if self.status[id] != false {
                        for workspace in (self.workspaces[id] ?? [:]).values {
                            if !workspace.title.hasPrefix("⏸ ") { workspace.customTitle = "⏸ " + workspace.title }
                        }
                    }
                    self.status[id] = false; self.onChange?()
                }
                self.revision &+= 1
                try? await Task.sleep(nanoseconds: 2_000_000_000)
            }
        }
        onChange?()
    }
    func reconnectSaved() {
        Task { [weak self] in
            let saved = await LocalPeerCredentialStore.loadSaved()
            guard let self else { return }
            for credential in saved where self.clients[credential.hostID] == nil {
                self.connect(LocalPeerClient(credential))
            }
        }
    }
    func disconnect(_ id: String, forget: Bool = false) {
        tasks.removeValue(forKey: id)?.cancel()
        let removed = workspaces.removeValue(forKey: id) ?? [:]
        let removedIDs = Set(removed.values.map(\.id))
        for workspace in removed.values {
            if let owner = workspace.owningTabManager,
               owner.tabs.allSatisfy({ removedIDs.contains($0.id) }) {
                // An app window always needs one local workspace after detaching its last peer.
                _ = owner.addWorkspaceIfActive(inheritWorkingDirectory: false, select: false,
                    autoWelcomeIfNeeded: false)
            }
        }
        for workspace in removed.values {
            workspace.localPeerBinding?.stop()
            // Closing only the local projection never sends a close to its owner.
            workspace.owningTabManager?.closeWorkspace(workspace, recordHistory: false)
        }
        clients.removeValue(forKey: id)
        status.removeValue(forKey: id); revision &+= 1
        if forget { LocalPeerCredentialStore.forget(id) }
        onChange?()
    }
    func noteProjectionClosed(_ workspace: Workspace) {
        guard let binding = workspace.localPeerBinding else { return }
        hidden[binding.client.credential.hostID, default: []].insert(binding.remoteWorkspaceID)
    }
    func action(_ client: LocalPeerClient, _ fields: [String: Any]) async throws {
        _ = try await client.request("/v1/action", body: JSONSerialization.data(withJSONObject: fields))
        try await refresh(client)
    }
    func split(in workspace: Workspace, panelID: UUID?, direction: String) -> Bool {
        guard let binding = workspace.localPeerBinding,
              let mirror = binding.mirrors.values.first(where: { $0.panel?.id == panelID }) ?? binding.mirrors.values.first else { return false }
        Task {
            do { try await action(binding.client, ["action": "terminal.split", "workspace_id": binding.remoteWorkspaceID,
                "surface_id": mirror.remoteSurfaceID, "direction": direction]) }
            catch { present(error) }
        }
        return true
    }
    private func refresh(_ client: LocalPeerClient) async throws {
        let data = try await client.request("/v1/catalog")
        guard !Task.isCancelled, clients[client.credential.hostID] === client else { throw CancellationError() }
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              object["host_id"] as? String == client.credential.hostID,
              let records = object["workspaces"] as? [[String: Any]], records.count <= 256,
              records.reduce(0, { $0 + (($1["terminals"] as? [Any])?.count ?? 0) }) <= 512,
              let manager = manager() else { throw LocalPeerError.malformed }
        let host = client.credential.hostID
        var attached = workspaces[host] ?? [:]
        var presentIDs: Set<String> = []
        for record in records where record["peer_projection"] as? Bool != true {
            guard let remoteID = record["id"] as? String, UUID(uuidString: remoteID) != nil,
                  let terminals = record["terminals"] as? [[String: Any]], !terminals.isEmpty else { continue }
            presentIDs.insert(remoteID)
            if hidden[host]?.contains(remoteID) == true { continue }
            // Keep the session name readable in a narrow sidebar; provenance follows it.
            let title = (record["title"] as? String ?? "") + " · " + client.credential.hostName
            let workspace: Workspace
            if let existing = attached[remoteID], !existing.isRetiredFromOwningTabManager {
                workspace = existing
                if workspace.customTitle != title { workspace.customTitle = title }
                if workspace.title != title { workspace.title = title }
            } else {
                guard let created = manager.addWorkspaceIfActive(title: title, select: false,
                    eagerLoadTerminal: false, initialTerminalStartsOnFirstVisit: true,
                    placementOverride: .end,
                    autoWelcomeIfNeeded: false, autoRefreshMetadata: false) else { continue }
                workspace = created
                workspace.setCustomColor("#7AA2A9")
                workspace.localPeerBinding = LocalPeerWorkspaceBinding(client: client, workspaceID: remoteID)
                attached[remoteID] = workspace
            }
            guard let binding = workspace.localPeerBinding else { continue }
            var live: Set<String> = []
            var directoriesChanged = false
            for terminal in terminals {
                guard let surfaceID = terminal["id"] as? String, UUID(uuidString: surfaceID) != nil else { continue }
                live.insert(surfaceID)
                let directory = terminal["current_directory"] as? String ?? record["current_directory"] as? String ?? ""
                if let mirror = binding.mirrors[surfaceID] {
                    if mirror.directory != directory {
                        mirror.directory = directory; directoriesChanged = true
                        if let panel = mirror.panel {
                            workspace.updateRemotePanelDirectoryWithMetadata(panelId: panel.id, directory: directory)
                        }
                    }
                    continue
                }
                let mirror = LocalPeerMirror(client: client, workspaceID: remoteID, surfaceID: surfaceID, directory: directory)
                let oldPanels = binding.mirrors.isEmpty ? Set(workspace.panels.keys) : []
                if mirror.mount(in: workspace, title: terminal["title"] as? String ?? title) != nil {
                    binding.mirrors[surfaceID] = mirror
                    directoriesChanged = true
                    if let panel = mirror.panel {
                        workspace.updateRemotePanelDirectoryWithMetadata(panelId: panel.id, directory: directory)
                    }
                    // Remove the deferred default shell before the workspace's first visit.
                    let projected = Set(binding.mirrors.values.compactMap { $0.panel?.id })
                    for panelID in oldPanels where !projected.contains(panelID) {
                        _ = workspace.closePanel(panelID, force: true)
                    }
                }
            }
            for (id, mirror) in binding.mirrors where !live.contains(id) {
                mirror.stop()
                if let panel = mirror.panel { _ = workspace.closePanel(panel.id, force: true) }
                binding.mirrors.removeValue(forKey: id)
            }
            if directoriesChanged {
                NotificationCenter.default.post(name: .workspaceCurrentDirectoryDidChange, object: workspace,
                    userInfo: ["workspaceId": workspace.id, "presentedDirectoryOnly": true])
            }
        }
        for (id, workspace) in attached where !presentIDs.contains(id) {
            workspace.localPeerBinding?.stop(); workspace.owningTabManager?.closeWorkspace(workspace, recordHistory: false)
            attached.removeValue(forKey: id)
        }
        workspaces[host] = attached
        onChange?()
    }
    func present(_ error: Error) {
        let alert = NSAlert()
        alert.messageText = String(localized: "peer.title", defaultValue: "Trusted Computers…")
        alert.informativeText = error.localizedDescription
        alert.runModal()
    }
}
