import Foundation

enum LocalPeerError: Error, LocalizedError {
    case invalidInvitation, privateStorage, disconnected, denied, malformed, unavailableRuntime
    var errorDescription: String? {
        switch self {
        case .invalidInvitation: String(localized: "peer.error.invitation", defaultValue: "The invitation is invalid or expired. Create a new one on the other Mac.")
        case .privateStorage: String(localized: "peer.error.storage", defaultValue: "The pairing could not be saved securely.")
        case .disconnected: String(localized: "peer.error.disconnected", defaultValue: "The other Mac is unavailable. Its sessions continue running there.")
        case .denied: String(localized: "peer.error.denied", defaultValue: "Access was revoked or the action was refused. Pair the computers again if necessary.")
        case .malformed: String(localized: "peer.error.response", defaultValue: "The other Mac sent an incompatible response.")
        case .unavailableRuntime: String(localized: "peer.error.runtime", defaultValue: "The bundled sharing service is missing. Reinstall Developer.")
        }
    }
}
