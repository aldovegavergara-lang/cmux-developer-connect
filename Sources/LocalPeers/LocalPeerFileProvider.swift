import Foundation

/// Immutable peer and source-directory authority; URLSession synchronizes transport state.
final class LocalPeerFileProvider: RemoteFileExplorerProvider, @unchecked Sendable {
    let client: LocalPeerClient
    let workspaceID: String
    let surfaceID: String
    let homePath: String
    var remoteIdentity: String { "peer:" + client.credential.hostID + ":" + workspaceID + ":" + surfaceID }
    var displayTarget: String { client.credential.hostName }
    var isAvailable: Bool { client.credential.expiresAt > Date() }
    init(_ root: LocalPeerFileRoot) {
        client = root.client; workspaceID = root.remoteWorkspaceID
        surfaceID = root.remoteSurfaceID; homePath = root.path
    }
    func resolveHomePath() async throws -> String { homePath }
    private func request(path: String, operation: String, hidden: Bool = true) async throws -> Data {
        let body = try JSONSerialization.data(withJSONObject: ["workspace_id": workspaceID,
            "surface_id": surfaceID, "path": path, "operation": operation, "show_hidden": hidden])
        return try await client.request("/v1/files", body: body)
    }
    func listDirectory(path: String, showHidden: Bool) async throws -> [FileExplorerEntry] {
        let data = try await request(path: path, operation: "list", hidden: showHidden)
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let entries = object["entries"] as? [[String: Any]], entries.count <= 4096 else { throw LocalPeerError.malformed }
        return try entries.map { item in
            guard let name = item["name"] as? String, let path = item["path"] as? String,
                  let directory = item["is_directory"] as? Bool else { throw LocalPeerError.malformed }
            return FileExplorerEntry(name: name, path: path, isDirectory: directory)
        }
    }
    func downloadFile(path: String, to localURL: URL) async throws {
        let response = try await request(path: path, operation: "read")
        guard let object = try JSONSerialization.jsonObject(with: response) as? [String: Any],
              let encoded = object["data_b64"] as? String, let data = Data(base64Encoded: encoded),
              data.count <= 2 * 1024 * 1024 else { throw LocalPeerError.malformed }
        try data.write(to: localURL, options: .atomic)
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: localURL.path)
    }
}
