import Foundation

extension TerminalController {
    /// Local developer test controls. Never exported through the network or SSH relay.
    @MainActor
    func v2LocalPeerControl(method: String, params: [String: Any]) -> V2CallResult? {
        #if DEBUG
        guard method.hasPrefix("developer.peer.") else { return nil }
        guard let app = AppDelegate.shared else { return .err(code: "unavailable", message: "App unavailable", data: nil) }
        switch method {
        case "developer.peer.share":
            do {
                try app.localPeerHost.start(internet: params["internet"] as? Bool ?? false,
                    address: params["address"] as? String, port: params["port"] as? Int ?? 8444)
                return .ok(["accepted": true])
            } catch { return .err(code: "peer_unavailable", message: error.localizedDescription, data: nil) }
        case "developer.peer.status":
            return .ok(["running": app.localPeerHost.running, "error": app.localPeerHost.error,
                "invitation": app.localPeerHost.invitation, "endpoint": app.localPeerHost.endpoint,
                "clients": Array(app.localPeerCoordinator.clients.keys), "connected": app.localPeerCoordinator.status])
        case "developer.peer.connect":
            guard let encoded = params["invitation"] as? String else { return .err(code: "invalid_params", message: "Invitation required", data: nil) }
            Task { @MainActor in
                do { app.localPeerCoordinator.connect(try await LocalPeerClient.pair(LocalPeerInvitation(encoded))) }
                catch { app.localPeerHost.error = error.localizedDescription }
            }
            return .ok(["accepted": true])
        case "developer.peer.action":
            guard let id = params["host_id"] as? String, let client = app.localPeerCoordinator.clients[id],
                  let fields = params["action"] as? [String: Any] else { return .err(code: "invalid_params", message: "Peer and action required", data: nil) }
            Task { @MainActor in
                do { try await app.localPeerCoordinator.action(client, fields) }
                catch { app.localPeerHost.error = error.localizedDescription }
            }
            return .ok(["accepted": true])
        case "developer.peer.disconnect":
            if let id = params["host_id"] as? String { app.localPeerCoordinator.disconnect(id, forget: params["forget"] as? Bool ?? false) }
            return .ok(["accepted": true])
        case "developer.peer.stop": app.localPeerHost.stop(); return .ok(["accepted": true])
        default: return .err(code: "method_not_found", message: "Unknown developer peer method", data: nil)
        }
        #else
        return nil
        #endif
    }
}
