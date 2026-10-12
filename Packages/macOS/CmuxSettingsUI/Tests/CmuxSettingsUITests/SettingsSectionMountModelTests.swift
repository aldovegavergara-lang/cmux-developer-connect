import SwiftUI
import Testing
@testable import CmuxSettingsUI

/// Progressive section mounting for the settings window
/// (https://github.com/manaflow-ai/cmux/issues/12134): one section in the
/// first pass, one more per appearance, navigation mounts on demand.
@MainActor
@Suite("SettingsSectionMountModel")
struct SettingsSectionMountModelTests {
    private let order: [SettingsSectionID] = [.app, .themes, .terminal, .automation, .reset]

    @Test func devicesSitsBetweenCloudAndNetworkingInTheDetailStack() throws {
        let order = SettingsSectionMountModel.displayOrder
        let mobile = try #require(order.firstIndex(of: .mobile))
        #expect(Array(order[(mobile + 1)...].prefix(3)) == [.cloudMachines, .computers, .networking])
    }

    @Test func displayOrderGivesEverySectionASlotExceptTheEmbeddedBrowserImport() {
        let slots = Set(SettingsSectionMountModel.displayOrder)
        #expect(slots.count == SettingsSectionMountModel.displayOrder.count)
        #expect(slots == Set(SettingsSectionID.allCases.filter(\.isAvailable)))
        #expect(SettingsSectionMountModel.hostSection(for: .computers) == .computers)
    }

    @Test func firstPassMountsOnlyTheInitialSection() {
        let model = SettingsSectionMountModel(initial: .terminal, order: order)
        #expect(model.mounted == [.terminal])
        #expect(model.isMounted(.terminal))
        #expect(!model.isMounted(.app))
        #expect(!model.isComplete)
    }

    @Test func eachAppearanceMountsExactlyOneMoreSectionInDisplayOrder() {
        let model = SettingsSectionMountModel(initial: .terminal, order: order)
        var mountedInOrder: [SettingsSectionID] = []
        var current: SettingsSectionID? = .terminal
        while let section = current {
            current = model.sectionDidAppear(section)
            if let current { mountedInOrder.append(current) }
        }
        #expect(mountedInOrder == [.app, .themes, .automation, .reset])
        #expect(model.isComplete)
        #expect(model.mounted == Set(order))
        #expect(model.sectionDidAppear(.reset) == nil)
    }

    @Test func appearanceOfASectionThatIsNotTheChainHeadDoesNotAdvance() {
        let model = SettingsSectionMountModel(initial: .app, order: order)
        // Navigation mounts .automation out of band; its appearance must not
        // start a second chain (two sections per turn).
        #expect(model.ensureMounted(.automation) == false)
        #expect(model.sectionDidAppear(.automation) == nil)
        #expect(model.mounted == [.app, .automation])
        #expect(model.sectionDidAppear(.app) == .themes)
        #expect(model.sectionDidAppear(.themes) == .terminal)
        // .automation is already mounted, so the chain skips it.
        #expect(model.sectionDidAppear(.terminal) == .reset)
        // Everything is mounted, but the last mount is still under
        // construction until it appears.
        #expect(!model.isComplete)
        #expect(model.sectionDidAppear(.reset) == nil)
        #expect(model.isComplete)
    }

    @Test func ensureMountedReportsAlreadyMountedSections() {
        let model = SettingsSectionMountModel(initial: .app, order: order)
        #expect(model.ensureMounted(.app))
        #expect(model.ensureMounted(.reset) == false)
        #expect(model.ensureMounted(.reset))
    }

    @Test(arguments: [SettingsSectionID.account, .browser, .browserImport])
    func unavailableSectionsFallBackToApp(section: SettingsSectionID) {
        let model = SettingsSectionMountModel(initial: section, order: order)
        #expect(SettingsSectionMountModel.hostSection(for: section) == .app)
        #expect(model.mounted == [.app])
        #expect(model.isMounted(section))
        #expect(model.ensureMounted(section))
    }

    @Test func sectionsOutsideTheOrderCountAsMounted() {
        let model = SettingsSectionMountModel(initial: .app, order: [.app, .themes])
        #expect(model.isMounted(.cloudMachines))
        #expect(model.ensureMounted(.cloudMachines))
        #expect(model.mounted == [.app])
    }

    @Test func initialSectionOutsideTheOrderFallsBackToTheFirstSlot() {
        let model = SettingsSectionMountModel(initial: .cloudMachines, order: [.app, .themes])
        #expect(model.mounted == [.app])
        #expect(model.sectionDidAppear(.app) == .themes)
    }

    @Test func completionWaitsForTheFinalSectionToAppear() {
        let model = SettingsSectionMountModel(initial: .app, order: [.app, .themes])
        #expect(!model.isComplete)
        #expect(model.sectionDidAppear(.app) == .themes)
        #expect(model.mounted == Set([.app, .themes]))
        #expect(!model.isComplete, "the App section is mounted but has not appeared yet")
        #expect(model.sectionDidAppear(.themes) == nil)
        #expect(model.isComplete)
    }

    @Test func deferredScrollIsOwedToItsSectionOnly() {
        let model = SettingsSectionMountModel(initial: .app, order: order)
        let target = SettingsSectionScrollTarget(
            section: .automation, anchorID: "section:automation", anchor: .top, generation: 3
        )
        model.deferScroll(target)
        #expect(model.takeDeferredScroll(for: .themes) == nil)
        #expect(model.takeDeferredScroll(for: .automation) == target)
        #expect(model.takeDeferredScroll(for: .automation) == nil)
        model.deferScroll(target)
        model.cancelDeferredScroll()
        #expect(model.deferredScroll == nil)
    }

    @Test func pinnedScrollTracksTheLatestNavigation() {
        let model = SettingsSectionMountModel(initial: .app, order: order)
        let first = SettingsSectionScrollTarget(section: .reset, anchorID: "section:reset", anchor: .top, generation: 1)
        let second = SettingsSectionScrollTarget(section: .themes, anchorID: "row:app", anchor: .center, generation: 2)
        model.pin(first)
        model.pin(second)
        #expect(model.pinnedScroll == second)
    }
}
