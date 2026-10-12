import AppKit
import Combine
import Darwin
import Foundation

/// One opt-in service for this app, independent of all its terminal sessions.
@MainActor
final class LocalPeerHost: ObservableObject {
    @Published private(set) var invitation = ""
    @Published private(set) var endpoint = ""
    @Published private(set) var peers: [[String: String]] = []
    @Published private(set) var running = false
    @Published var error = ""
    private var process: Process?
    private var commands: FileHandle?
    private var refresh: Task<Void, Never>?

    func start(internet: Bool = false, address: String? = nil, port: Int = 8444) throws {
        guard process == nil else { invite(); return }
        guard let socket = TerminalController.shared.currentSocketPathForRemoteRestore(),
              let resources = Bundle.main.resourceURL,
              let address = address ?? Self.address(internet: internet) else { throw LocalPeerError.disconnected }
        let attributes = try FileManager.default.attributesOfItem(atPath: socket)
        guard attributes[.type] as? FileAttributeType == .typeSocket,
              (attributes[.ownerAccountID] as? NSNumber)?.uint32Value == getuid() else { throw LocalPeerError.denied }
        // Sharing never exposes the local control socket to other users of this Mac.
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: socket)
        let bundled = resources.appendingPathComponent("peer-runtime/bin/python3")
        let runtime: URL
        if FileManager.default.isExecutableFile(atPath: bundled.path) { runtime = bundled }
        else {
            #if DEBUG
            runtime = URL(fileURLWithPath: "/opt/homebrew/bin/python3")
            #else
            throw LocalPeerError.unavailableRuntime
            #endif
        }
        let state = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".local/state/cmux-developer/peers")
            .appendingPathComponent(Bundle.main.bundleIdentifier ?? "developer")
            .appendingPathComponent(internet ? "tailscale" : "lan")
        let child = Process(), input = Pipe(), output = Pipe()
        child.executableURL = runtime
        child.arguments = ["-I", "-B", resources.appendingPathComponent("bin/cmux-peer-service.py").path,
            "--socket", socket, "--bind", address, "--port", String(port), "--state-dir", state.path,
            "--name", Host.current().localizedName ?? "Mac"] + (internet ? ["--internet"] : [])
        child.environment = ["PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "en_US.UTF-8"]
        child.standardInput = input; child.standardOutput = output; child.standardError = FileHandle.nullDevice
        child.terminationHandler = { [weak self] child in
            Task { @MainActor in
                guard let self, self.process === child else { return }
                self.running = false; self.process = nil; self.commands = nil
                self.invitation = ""; self.endpoint = ""; self.refresh?.cancel()
                if child.terminationStatus != 0 { self.error = LocalPeerError.disconnected.localizedDescription }
            }
        }
        try child.run()
        process = child; commands = input.fileHandleForWriting; running = true; error = ""
        // Blocking pipe reads live on a utility queue, never the AppKit or typing path.
        let handle = output.fileHandleForReading
        DispatchQueue.global(qos: .utility).async { [weak self] in
            var buffer = Data()
            while true {
                let bytes = handle.availableData
                if bytes.isEmpty { break }
                buffer.append(bytes)
                if buffer.count > 65536 { break }
                while let newline = buffer.firstIndex(of: 10) {
                    let line = Data(buffer[..<newline]); buffer.removeSubrange(...newline)
                    Task { @MainActor [weak self] in self?.receive(line) }
                }
            }
            try? handle.close()
        }
        refresh = Task { [weak self] in
            while !Task.isCancelled {
                self?.send(["command": "peers"])
                try? await Task.sleep(nanoseconds: 3_000_000_000)
            }
        }
    }
    func invite() { invitation = ""; send(["command": "invite"]) }
    func revoke(_ id: String) { send(["command": "revoke", "client_id": id]); send(["command": "peers"]) }
    func stop() {
        refresh?.cancel(); refresh = nil
        send(["command": "stop"])
        try? commands?.close(); commands = nil
        process?.terminate(); process = nil; running = false
        invitation = ""; endpoint = ""; peers = []
    }
    private func send(_ value: [String: String]) {
        guard let data = try? JSONSerialization.data(withJSONObject: value) else { return }
        try? commands?.write(contentsOf: data + Data([10]))
    }
    private func receive(_ data: Data) {
        guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return }
        if object["event"] as? String == "invitation" {
            invitation = object["invitation"] as? String ?? ""; endpoint = object["endpoint"] as? String ?? ""
        } else if let records = object["peers"] as? [[String: Any]] {
            peers = records.compactMap { row in
                guard let id = row["id"] as? String, let name = row["name"] as? String else { return nil }
                return ["id": id, "name": name]
            }
        }
    }
    private static func address(internet: Bool) -> String? {
        var head: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&head) == 0 else { return nil }
        defer { freeifaddrs(head) }
        var node = head
        var candidates: [(String, String)] = []
        while let current = node {
            defer { node = current.pointee.ifa_next }
            guard let raw = current.pointee.ifa_addr, raw.pointee.sa_family == UInt8(AF_INET) else { continue }
            var bytes = [CChar](repeating: 0, count: Int(NI_MAXHOST))
            guard getnameinfo(raw, socklen_t(raw.pointee.sa_len), &bytes, socklen_t(bytes.count), nil, 0, NI_NUMERICHOST) == 0 else { continue }
            let ip = String(cString: bytes), name = String(cString: current.pointee.ifa_name)
            guard LocalPeerInvitation.isPrivateAddress(ip), !ip.hasPrefix("127.") else { continue }
            let tail = ip.hasPrefix("100.")
            if tail == internet { candidates.append((name, ip)) }
        }
        return candidates.sorted {
            let left = $0.0.hasPrefix("en"), right = $1.0.hasPrefix("en")
            return left == right ? $0.0 < $1.0 : left
        }.first?.1
    }
}
