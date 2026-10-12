import CmuxCommandPalette
import AppKit
import Foundation

extension ContentView {
    static let commandPaletteProUpgradeCommandId = "palette.pro.upgrade"
    static let commandPaletteProWelcomeChecklistCommandId = "palette.pro.welcomeChecklist"

    static func commandPaletteProCommandContributions() -> [CommandPaletteCommandContribution] {
        []
    }

    func registerProCommandHandlers(_ registry: inout CommandPaletteHandlerRegistry) {
        registry.register(commandId: Self.commandPaletteProUpgradeCommandId) {
#if DEBUG
            cmuxDebugLog("palette.pro.upgrade.invoke")
#endif
            ProUpgradePresenter.present(source: .commandPalette)
        }
        registry.register(commandId: Self.commandPaletteProWelcomeChecklistCommandId) {
#if DEBUG
            cmuxDebugLog("palette.pro.welcomeChecklist.invoke")
#endif
            ProWelcomeChecklistPresenter.present()
        }
    }
}
