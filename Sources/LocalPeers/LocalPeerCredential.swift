import Foundation
import Security

struct LocalPeerCredential: Codable, Sendable {
    let hostID: String
    let hostName: String
    let endpoint: URL
    let certificate: Data
    let clientID: String
    let token: String
    let expiresAt: Date
}

struct LocalPeerInvitation: Sendable {
    let hostID: String
    let hostName: String
    let endpoint: URL
    let certificate: Data
    let secret: String

    init(_ encoded: String) throws {
        let value = encoded.trimmingCharacters(in: .whitespacesAndNewlines)
        guard value.hasPrefix("cmux-peer-v1:"), value.utf8.count < 16384 else { throw LocalPeerError.invalidInvitation }
        var base64 = String(value.dropFirst("cmux-peer-v1:".count)).replacingOccurrences(of: "-", with: "+").replacingOccurrences(of: "_", with: "/")
        base64 += String(repeating: "=", count: (4 - base64.count % 4) % 4)
        guard let data = Data(base64Encoded: base64),
              let object = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              object["protocol"] as? Int == 1,
              let hostID = object["host_id"] as? String, UUID(uuidString: hostID) != nil,
              let hostName = object["host_name"] as? String, hostName.utf8.count <= 128,
              let endpointString = object["endpoint"] as? String,
              let endpoint = URL(string: endpointString), endpoint.scheme == "https",
              endpoint.user == nil, endpoint.password == nil, endpoint.query == nil, endpoint.fragment == nil,
              (endpoint.path.isEmpty || endpoint.path == "/"),
              let address = endpoint.host, Self.isPrivateAddress(address),
              let certString = object["certificate_der"] as? String,
              let certificate = Data(base64Encoded: certString), certificate.count < 8192,
              SecCertificateCreateWithData(nil, certificate as CFData) != nil,
              let secret = object["invitation"] as? String, secret.utf8.count == 43,
              let expiry = object["expires_at"] as? Double,
              expiry > Date().timeIntervalSince1970, expiry <= Date().timeIntervalSince1970 + 190
        else { throw LocalPeerError.invalidInvitation }
        self.hostID = hostID; self.hostName = hostName; self.endpoint = endpoint
        self.certificate = certificate; self.secret = secret
    }

    static func isPrivateAddress(_ host: String) -> Bool {
        let labels = host.split(separator: ".", omittingEmptySubsequences: false)
        guard labels.count == 4, labels.allSatisfy({
            !$0.isEmpty && $0.utf8.allSatisfy({ (48...57).contains($0) }) && ($0.count == 1 || $0.first != "0")
        }) else { return false }
        let parts = labels.compactMap { Int($0) }
        guard parts.count == 4, parts.allSatisfy({ (0...255).contains($0) }) else { return false }
        return parts[0] == 127 || parts[0] == 10 ||
            (parts[0] == 172 && (16...31).contains(parts[1])) ||
            (parts[0] == 192 && parts[1] == 168) ||
            (parts[0] == 100 && (64...127).contains(parts[1]))
    }
}

enum LocalPeerCredentialStore {
    private static var service: String { (Bundle.main.bundleIdentifier ?? "com.cmux.developer") + ".trusted-peers" }
    static func save(_ credential: LocalPeerCredential) throws {
        let data = try JSONEncoder().encode(credential)
        let key: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service, kSecAttrAccount as String: credential.hostID]
        SecItemDelete(key as CFDictionary)
        var attributes = key
        attributes[kSecValueData as String] = data
        attributes[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        guard SecItemAdd(attributes as CFDictionary, nil) == errSecSuccess else { throw LocalPeerError.privateStorage }
    }
    static func all() -> [LocalPeerCredential] {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service, kSecMatchLimit as String: kSecMatchLimitAll,
            kSecReturnAttributes as String: true]
        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let records = result as? [[String: Any]] else { return [] }
        // macOS rejects returning password data with MatchLimitAll. Enumerate
        // this app's attributes, then read each specific credential with its ACL.
        return records.compactMap { item -> LocalPeerCredential? in
            guard let account = item[kSecAttrAccount as String] as? String else { return nil }
            let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
                kSecAttrService as String: service, kSecAttrAccount as String: account,
                kSecMatchLimit as String: kSecMatchLimitOne, kSecReturnData as String: true]
            var value: CFTypeRef?
            guard SecItemCopyMatching(query as CFDictionary, &value) == errSecSuccess,
                  let data = value as? Data else { return nil }
            return try? JSONDecoder().decode(LocalPeerCredential.self, from: data)
        }
            .filter { $0.expiresAt > Date() }
    }
    static func loadSaved() async -> [LocalPeerCredential] {
        await withCheckedContinuation { continuation in
            DispatchQueue.global(qos: .utility).async {
                continuation.resume(returning: all())
            }
        }
    }
    static func forget(_ id: String) {
        SecItemDelete([kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service, kSecAttrAccount as String: id] as CFDictionary)
    }
}
