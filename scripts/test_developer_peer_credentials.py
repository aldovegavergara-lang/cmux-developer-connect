#!/usr/bin/env python3
"""Actual macOS Keychain round-trip of the production store, in an isolated service."""
import pathlib,re,secrets,subprocess,tempfile
repo=pathlib.Path(__file__).resolve().parents[1]
source=(repo/'Sources/LocalPeers/LocalPeerCredential.swift').read_text()
store='enum LocalPeerCredentialStore {'+source.split('enum LocalPeerCredentialStore {',1)[1]
service='cmux.developer.test.credentials.'+secrets.token_hex(12)
store=re.sub(r'private static var service: String \{[^\n]+\}', 'private static var service: String { "'+service+'" }',store,count=1)
fixture='''import Foundation
import Security
struct LocalPeerCredential: Codable { let hostID: String; let expiresAt: Date }
enum LocalPeerError: Error { case privateStorage }
'''+store+'''
let live = LocalPeerCredential(hostID: UUID().uuidString, expiresAt: Date().addingTimeInterval(3600))
let expired = LocalPeerCredential(hostID: UUID().uuidString, expiresAt: Date().addingTimeInterval(-60))
defer { LocalPeerCredentialStore.forget(live.hostID); LocalPeerCredentialStore.forget(expired.hostID) }
try LocalPeerCredentialStore.save(live)
try LocalPeerCredentialStore.save(expired)
let saved = LocalPeerCredentialStore.all()
guard saved.count == 1, saved.first?.hostID == live.hostID else {
 LocalPeerCredentialStore.forget(live.hostID); LocalPeerCredentialStore.forget(expired.hostID)
 FileHandle.standardError.write(Data("FAIL: actual macOS Keychain cannot recover the saved live credential\\n".utf8)); exit(1)
}
LocalPeerCredentialStore.forget(live.hostID)
precondition(LocalPeerCredentialStore.all().isEmpty)
print("PASS: actual macOS Keychain saves, enumerates, excludes expired credentials and forgets")
'''
with tempfile.TemporaryDirectory(prefix='cmux-peer-keychain-') as temporary:
 folder=pathlib.Path(temporary);code=folder/'main.swift';program=folder/'test';code.write_text(fixture)
 subprocess.run(['xcrun','swiftc',str(code),'-o',str(program)],check=True)
 subprocess.run(['codesign','--force','--sign','-',str(program)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 subprocess.run([str(program)],check=True)
