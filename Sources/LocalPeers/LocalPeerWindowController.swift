import AppKit
import SwiftUI

@MainActor
final class LocalPeerWindowController: NSWindowController {
    init(coordinator: LocalPeerCoordinator, host: LocalPeerHost) {
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 650, height: 640),
            styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
        window.title = String(localized: "peer.title", defaultValue: "Trusted Computers…")
        window.contentView = NSHostingView(rootView: LocalPeerView(coordinator: coordinator, host: host))
        window.isReleasedWhenClosed = false
        super.init(window: window)
    }
    required init?(coder: NSCoder) { nil }
    override func showWindow(_ sender: Any?) {
        window?.center(); super.showWindow(sender); window?.makeKeyAndOrderFront(sender)
    }
}

private struct LocalPeerView: View {
    @ObservedObject var coordinator: LocalPeerCoordinator
    @ObservedObject var host: LocalPeerHost
    @State private var invitation = ""
    @State private var busy = false
    @State private var internet = false
    @State private var error = ""
    @State private var name = ""

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Label(String(localized: "peer.heading", defaultValue: "Your Macs, together"), systemImage: "desktopcomputer")
                    .font(.title2.bold())
                Text(String(localized: "peer.explanation", defaultValue: "Share this app's sessions. Both Macs can use the same terminals; sessions keep running on their original Mac."))
                    .foregroundStyle(.secondary)
                GroupBox {
                    VStack(alignment: .leading, spacing: 12) {
                        Text(String(localized: "peer.share", defaultValue: "Share this Mac")).font(.headline)
                        Toggle(String(localized: "peer.internet", defaultValue: "Use Tailscale for Internet access"), isOn: $internet).disabled(host.running)
                        Text(String(localized: "peer.grant", defaultValue: "The invitation grants control of all current and future sessions and read access to their working directories. Give it only to your own trusted Mac. It expires in three minutes and works once."))
                            .font(.callout).foregroundStyle(.secondary)
                        HStack {
                            if host.running {
                                Label(host.endpoint, systemImage: "lock.shield")
                                Spacer()
                                Button(String(localized: "peer.stop", defaultValue: "Stop Sharing")) { host.stop() }
                            } else {
                                Button(String(localized: "peer.start", defaultValue: "Share App")) {
                                    do { try host.start(internet: internet) } catch { self.error = error.localizedDescription }
                                }.buttonStyle(.borderedProminent)
                            }
                        }
                        if host.running {
                            HStack {
                                Button(String(localized: "peer.copy", defaultValue: "Copy Invitation")) {
                                    NSPasteboard.general.clearContents(); NSPasteboard.general.setString(host.invitation, forType: .string)
                                }.disabled(host.invitation.isEmpty)
                                Button(String(localized: "peer.renew", defaultValue: "New Invitation")) { host.invite() }
                            }
                            ForEach(host.peers, id: \.self) { peer in
                                HStack {
                                    Text(peer["name"] ?? "Mac"); Spacer()
                                    Button(String(localized: "peer.revoke", defaultValue: "Revoke Access")) { if let id = peer["id"] { host.revoke(id) } }
                                }
                            }
                        }
                    }.frame(maxWidth: .infinity, alignment: .leading).padding(6)
                }
                GroupBox {
                    VStack(alignment: .leading, spacing: 12) {
                        Text(String(localized: "peer.connect", defaultValue: "Connect to another Mac")).font(.headline)
                        TextField(String(localized: "peer.paste", defaultValue: "Paste the invitation from the other Mac"), text: $invitation)
                            .textFieldStyle(.roundedBorder)
                        Button(String(localized: "peer.pair", defaultValue: "Connect")) {
                            busy = true; error = ""
                            Task { @MainActor in
                                defer { busy = false }
                                do {
                                    let decoded = try LocalPeerInvitation(invitation)
                                    let client = try await LocalPeerClient.pair(decoded)
                                    coordinator.connect(client); invitation = ""
                                } catch { self.error = error.localizedDescription }
                            }
                        }.disabled(busy || invitation.isEmpty)
                        Button(String(localized: "peer.reconnect", defaultValue: "Reconnect Saved Macs")) { coordinator.reconnectSaved() }
                        ForEach(Array(coordinator.clients.keys).sorted(), id: \.self) { id in
                            if let client = coordinator.clients[id] {
                                HStack {
                                    Label(client.credential.hostName, systemImage: coordinator.status[id] == true ? "checkmark.circle.fill" : "wifi.slash")
                                    Spacer()
                                    Button(String(localized: "peer.disconnect", defaultValue: "Disconnect")) { coordinator.disconnect(id) }
                                    Button(String(localized: "peer.forget", defaultValue: "Forget")) { coordinator.disconnect(id, forget: true) }
                                }
                            }
                        }
                    }.frame(maxWidth: .infinity, alignment: .leading).padding(6)
                }
                if let workspace = AppDelegate.shared?.tabManager?.selectedWorkspace, let binding = workspace.localPeerBinding {
                    GroupBox {
                        VStack(alignment: .leading, spacing: 10) {
                            Text(String(localized: "peer.actions", defaultValue: "Actions on the original Mac")).font(.headline)
                            TextField(String(localized: "peer.name", defaultValue: "Session name"), text: $name)
                            HStack {
                                Button(String(localized: "peer.new", defaultValue: "New Session")) { action(binding, ["action": "workspace.new", "title": name.isEmpty ? "Remote" : name]) }
                                Button(String(localized: "peer.rename", defaultValue: "Rename Session")) { action(binding, ["action": "workspace.rename", "workspace_id": binding.remoteWorkspaceID, "title": name]) }.disabled(name.isEmpty)
                                Button(String(localized: "peer.split", defaultValue: "Split Terminal")) { _ = coordinator.split(in: workspace, panelID: workspace.focusedPanelId, direction: "right") }
                                Button(String(localized: "peer.close", defaultValue: "Close Original Session")) {
                                    let alert = NSAlert()
                                    alert.messageText = String(localized: "peer.confirmClose", defaultValue: "Close this session on its original Mac?")
                                    alert.informativeText = String(localized: "peer.closeDetail", defaultValue: "This ends the session for both computers. Disconnect instead to leave it running.")
                                    alert.addButton(withTitle: String(localized: "peer.close", defaultValue: "Close Original Session"))
                                    alert.addButton(withTitle: String(localized: "peer.cancel", defaultValue: "Cancel"))
                                    if alert.runModal() == .alertFirstButtonReturn {
                                        action(binding, ["action": "workspace.close", "workspace_id": binding.remoteWorkspaceID, "confirmed": true])
                                    }
                                }
                            }
                        }.padding(6)
                    }
                }
                if !error.isEmpty || !host.error.isEmpty { Text(error.isEmpty ? host.error : error).foregroundStyle(.red) }
            }.padding(24)
        }.frame(minWidth: 610, minHeight: 530)
    }
    private func action(_ binding: LocalPeerWorkspaceBinding, _ fields: [String: Any]) {
        Task { @MainActor in
            do { try await coordinator.action(binding.client, fields) } catch { self.error = error.localizedDescription }
        }
    }
}
