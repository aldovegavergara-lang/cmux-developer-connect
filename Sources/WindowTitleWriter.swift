import AppKit

/// Deduplicates main-window title writes at the AppKit boundary.
///
/// Terminal-title rate limiting is owned upstream by
/// ``GhosttyTitleUpdateDispatcher`` and the TabManager/Dock panel coalescer.
/// This writer deliberately owns no pending state or timer; it only prevents
/// an unchanged title from becoming another Dock/Spaces mutation.
@MainActor
final class WindowTitleWriter {
    nonisolated private static let appName = Bundle.main.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String ?? "cmux Developer"
    nonisolated static func displayTitle(for title: String) -> String {
        title.isEmpty ? appName : "\(appName) — \(title)"
    }

    func apply(_ title: String, to window: NSWindow) {
        let displayTitle = Self.displayTitle(for: title)
        guard window.title != displayTitle else { return }
        window.title = displayTitle
    }
}
