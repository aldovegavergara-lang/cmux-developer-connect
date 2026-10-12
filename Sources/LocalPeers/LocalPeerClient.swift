import Foundation

/// Immutable admitted peer; Foundation synchronizes the URLSession internals.
final class LocalPeerClient: @unchecked Sendable {
    let credential: LocalPeerCredential
    private let session: URLSession
    private let controlSession: URLSession
    init(_ credential: LocalPeerCredential) {
        self.credential = credential
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 8
        configuration.timeoutIntervalForResource = 10
        configuration.httpShouldSetCookies = false
        configuration.urlCache = nil
        configuration.httpMaximumConnectionsPerHost = 2
        session = URLSession(configuration: configuration,
            delegate: LocalPeerPinnedSessionDelegate(certificate: credential.certificate), delegateQueue: nil)
        let controls = configuration.copy() as! URLSessionConfiguration
        controls.httpMaximumConnectionsPerHost = 1
        controlSession = URLSession(configuration: controls,
            delegate: LocalPeerPinnedSessionDelegate(certificate: credential.certificate), delegateQueue: nil)
    }
    deinit {
        session.invalidateAndCancel()
        controlSession.invalidateAndCancel()
    }
    #if compiler(>=6.2)
    @concurrent
    #endif
    nonisolated func request(_ path: String, body: Data? = nil) async throws -> Data {
        guard credential.expiresAt > Date(), path.hasPrefix("/v1/"), !path.contains(".."),
              credential.endpoint.scheme == "https", credential.endpoint.user == nil,
              credential.endpoint.password == nil, credential.endpoint.query == nil, credential.endpoint.fragment == nil,
              (credential.endpoint.path.isEmpty || credential.endpoint.path == "/"),
              let address = credential.endpoint.host, LocalPeerInvitation.isPrivateAddress(address)
        else { throw LocalPeerError.denied }
        var request = URLRequest(url: credential.endpoint.appendingPathComponent(String(path.dropFirst())))
        request.setValue("Bearer " + credential.token, forHTTPHeaderField: "Authorization")
        if let body {
            request.httpMethod = "POST"; request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        let transport = ["/v1/input", "/v1/action", "/v1/pair"].contains(path) ? controlSession : session
        let (bytes, response) = try await transport.bytes(for: request)
        defer { bytes.task.cancel() }
        guard let http = response as? HTTPURLResponse else { throw LocalPeerError.malformed }
        guard http.statusCode == 200 else { throw http.statusCode == 401 || http.statusCode == 403 ? LocalPeerError.denied : LocalPeerError.disconnected }
        guard response.expectedContentLength <= 4 * 1024 * 1024 else { throw LocalPeerError.malformed }
        var data = Data()
        data.reserveCapacity(16384)
        for try await byte in bytes {
            guard data.count < 4 * 1024 * 1024 else { throw LocalPeerError.malformed }
            data.append(byte)
        }
        guard data.count <= 4 * 1024 * 1024,
              let object = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              object["ok"] as? Bool == true, let result = object["result"] else { throw LocalPeerError.malformed }
        return try JSONSerialization.data(withJSONObject: result)
    }
    @MainActor
    static func pair(_ invitation: LocalPeerInvitation) async throws -> LocalPeerClient {
        let clientID = UUID().uuidString
        let tentative = LocalPeerCredential(hostID: invitation.hostID, hostName: invitation.hostName,
            endpoint: invitation.endpoint, certificate: invitation.certificate, clientID: clientID,
            token: "", expiresAt: Date().addingTimeInterval(180))
        let transport = LocalPeerClient(tentative)
        let body = try JSONSerialization.data(withJSONObject: ["invitation": invitation.secret,
            "client_id": clientID, "name": Host.current().localizedName ?? "Mac"])
        let data = try await transport.request("/v1/pair", body: body)
        guard let result = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              result["host_id"] as? String == invitation.hostID,
              result["client_id"] as? String == clientID.uppercased(),
              let token = result["token"] as? String, token.utf8.count == 43,
              let expiry = result["expires_at"] as? Double,
              expiry > Date().timeIntervalSince1970, expiry <= Date().timeIntervalSince1970 + 31 * 86400
        else { throw LocalPeerError.malformed }
        let credential = LocalPeerCredential(hostID: invitation.hostID, hostName: invitation.hostName,
            endpoint: invitation.endpoint, certificate: invitation.certificate, clientID: clientID,
            token: token, expiresAt: Date(timeIntervalSince1970: expiry))
        try LocalPeerCredentialStore.save(credential)
        return LocalPeerClient(credential)
    }
}
