import Foundation
import Security

/// Immutable certificate pin; URLSession owns callback synchronization.
final class LocalPeerPinnedSessionDelegate: NSObject, URLSessionDelegate, URLSessionTaskDelegate, @unchecked Sendable {
    private let certificate: Data
    init(certificate: Data) { self.certificate = certificate }
    func urlSession(_ session: URLSession, didReceive challenge: URLAuthenticationChallenge,
                    completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) {
        guard challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust,
              let trust = challenge.protectionSpace.serverTrust,
              let chain = SecTrustCopyCertificateChain(trust) as? [SecCertificate], let leaf = chain.first,
              Data(SecCertificateCopyData(leaf) as Data) == certificate else {
            completionHandler(.cancelAuthenticationChallenge, nil); return
        }
        // The invitation is the only trust anchor. Hostname and SSL policy remain enabled.
        SecTrustSetAnchorCertificates(trust, [leaf] as CFArray)
        SecTrustSetAnchorCertificatesOnly(trust, true)
        guard SecTrustEvaluateWithError(trust, nil) else {
            completionHandler(.cancelAuthenticationChallenge, nil); return
        }
        completionHandler(.useCredential, URLCredential(trust: trust))
    }
    func urlSession(_ session: URLSession, task: URLSessionTask, didReceive challenge: URLAuthenticationChallenge,
                    completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) {
        // AsyncBytes supplies task-level challenges; use exactly the same pinned trust decision.
        urlSession(session, didReceive: challenge, completionHandler: completionHandler)
    }
    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest,
                    completionHandler: @escaping (URLRequest?) -> Void) {
        // Never forward a pairing secret or token to another endpoint.
        completionHandler(nil)
    }
}
