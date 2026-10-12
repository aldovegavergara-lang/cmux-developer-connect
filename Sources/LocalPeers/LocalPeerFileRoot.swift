import Foundation

struct LocalPeerFileRoot: Equatable {
    let workspaceID: UUID
    let remoteWorkspaceID: String
    let remoteSurfaceID: String
    let path: String
    let client: LocalPeerClient
    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.workspaceID == rhs.workspaceID && lhs.remoteWorkspaceID == rhs.remoteWorkspaceID &&
            lhs.remoteSurfaceID == rhs.remoteSurfaceID && lhs.path == rhs.path && lhs.client === rhs.client
    }
}
