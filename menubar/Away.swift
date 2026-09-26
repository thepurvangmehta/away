// Away: a menu bar moon for the Away plugin for Claude Code.
// Moon outline = off, filled moon = on. The number next to it = "Needs you" items from the last run.
// It reads the same files the plugin writes (~/.claude/away.on, ~/.claude/away.log)
// and toggles by running the plugin's own script, so there is one source of truth.
import AppKit
import ServiceManagement

let home = FileManager.default.homeDirectoryForCurrentUser.path
let flagPath = "\(home)/.claude/away.on"
let logPath = "\(home)/.claude/away.log"

struct Run {
    var refused: [String] = [], approved = 0, answered = 0, nudged = 0
}

func lastRun() -> Run {
    guard let text = try? String(contentsOfFile: logPath, encoding: .utf8) else { return Run() }
    let lines = text.split(separator: "\n").map(String.init)
    let start = lines.lastIndex { $0.contains("--- ON") } ?? 0
    var run = Run()
    for line in lines[start...] {
        if line.contains("  REFUSED") {
            // "27 Sep 03:23  REFUSED   (deleting files) Bash: rm -rf build" -> "deleting files: rm -rf build"
            let body = line.components(separatedBy: "REFUSED").last!.trimmingCharacters(in: .whitespaces)
            let why = body.components(separatedBy: ")").first!.replacingOccurrences(of: "(", with: "")
            let what = body.components(separatedBy: ": ").dropFirst().joined(separator: ": ")
            run.refused.append("\(why): \(what.prefix(70))")
        } else if line.contains("  APPROVED") { run.approved += 1 }
        else if line.contains("  ANSWERED") { run.answered += 1 }
        else if line.contains("  NUDGED") { run.nudged += 1 }
    }
    return run
}

// Newest installed copy of the plugin's script.
func scriptPath() -> String? {
    let base = "\(home)/.claude/plugins/cache/away/away"
    let versions = (try? FileManager.default.contentsOfDirectory(atPath: base)) ?? []
    return versions
        .sorted { $0.compare($1, options: .numeric) == .orderedAscending }
        .map { "\(base)/\($0)/scripts/away.py" }
        .last { FileManager.default.fileExists(atPath: $0) }
}

final class App: NSObject, NSApplicationDelegate, NSMenuDelegate {
    let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    var seenRefusals = 0  // ponytail: in-memory only; the badge comes back after a relaunch

    func applicationDidFinishLaunching(_ note: Notification) {
        item.menu = NSMenu()
        item.menu!.delegate = self
        refresh()
        Timer.scheduledTimer(withTimeInterval: 3, repeats: true) { [weak self] _ in self?.refresh() }
    }

    var isOn: Bool { FileManager.default.fileExists(atPath: flagPath) }

    func refresh() {
        let run = lastRun()
        let badge = run.refused.count > seenRefusals ? run.refused.count : 0
        let image = NSImage(systemSymbolName: isOn ? "moon.fill" : "moon",
                            accessibilityDescription: isOn ? "Away is on" : "Away is off")!
        image.isTemplate = true
        item.button?.image = image
        item.button?.title = badge > 0 ? " \(badge)" : ""
        item.button?.imagePosition = .imageLeading
        item.button?.toolTip = isOn ? "Away is on" : "Away is off"
    }

    func menuNeedsUpdate(_ menu: NSMenu) {
        menu.removeAllItems()
        let run = lastRun()
        seenRefusals = run.refused.count  // opening the menu clears the badge
        refresh()

        var since = ""
        if isOn, let s = try? String(contentsOfFile: flagPath, encoding: .utf8) { since = " since \(s)" }
        menu.addItem(disabled(isOn ? "Away is on\(since)" : "Away is off"))
        menu.addItem(action(isOn ? "Turn off (I'm in)" : "Turn on (I'm going to sleep)", #selector(toggle)))
        menu.addItem(.separator())

        if run.approved + run.answered + run.refused.count > 0 {
            menu.addItem(disabled(isOn ? "Tonight so far" : "Last time"))
            menu.addItem(disabled("\(run.approved) approved · \(run.answered) answered for you"))
        }
        let needs = NSMenuItem(title: "Needs you (\(run.refused.count))", action: nil, keyEquivalent: "")
        if !run.refused.isEmpty {
            let sub = NSMenu()
            run.refused.forEach { sub.addItem(disabled($0)) }
            needs.submenu = sub
        } else { needs.isEnabled = false }
        menu.addItem(needs)
        menu.addItem(action("Open full report", #selector(openReport)))
        menu.addItem(.separator())

        let login = action("Open at login", #selector(toggleLogin))
        login.state = SMAppService.mainApp.status == .enabled ? .on : .off
        menu.addItem(login)
        menu.addItem(NSMenuItem(title: "Quit", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"))
    }

    func disabled(_ title: String) -> NSMenuItem {
        let i = NSMenuItem(title: title, action: nil, keyEquivalent: ""); i.isEnabled = false; return i
    }
    func action(_ title: String, _ sel: Selector) -> NSMenuItem {
        let i = NSMenuItem(title: title, action: sel, keyEquivalent: ""); i.target = self; return i
    }

    @objc func toggle() {
        guard let script = scriptPath() else {
            let alert = NSAlert()
            alert.messageText = "Install the Away plugin first"
            alert.informativeText = "In Claude Code, run:\n/plugin marketplace add thepurvangmehta/away\n/plugin install away@away"
            alert.runModal()
            return
        }
        // A login shell, so python3 is found the same way it is in Terminal.
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/zsh")
        p.arguments = ["-lc", "python3 \"\(script)\" \(isOn ? "off" : "on") >/dev/null"]
        try? p.run()
        p.waitUntilExit()
        refresh()
    }

    @objc func openReport() {
        if !FileManager.default.fileExists(atPath: logPath) { FileManager.default.createFile(atPath: logPath, contents: nil) }
        NSWorkspace.shared.open(URL(fileURLWithPath: logPath))
    }

    @objc func toggleLogin() {
        let s = SMAppService.mainApp
        try? (s.status == .enabled ? s.unregister() : s.register())
    }
}

let app = NSApplication.shared
let delegate = App()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
