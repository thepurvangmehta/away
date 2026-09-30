// Away: a menu bar moon for the Away plugin for Claude Code.
// Moon outline = off, filled moon = on. The number next to it = "Needs you" items from the last run.
// Click it for a card: on or off, what happened, what needs you, and the switch.
// It reads the same files the plugin writes (~/.claude/away.on, ~/.claude/away.log)
// and toggles by running the plugin's own script, so there is one source of truth.
// `Away --snapshot out.png` draws the card to an image and quits (to check the design).
import AppKit
import ServiceManagement

let home = FileManager.default.homeDirectoryForCurrentUser.path
let flagPath = "\(home)/.claude/away.on"
let logPath = "\(home)/.claude/away.log"
let cardWidth: CGFloat = 300, pad: CGFloat = 16

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

func label(_ s: String, _ size: CGFloat, _ weight: NSFont.Weight = .regular,
           _ color: NSColor = .labelColor) -> NSTextField {
    let l = NSTextField(wrappingLabelWithString: s)
    l.font = .systemFont(ofSize: size, weight: weight)
    l.textColor = color
    l.isSelectable = false
    l.preferredMaxLayoutWidth = cardWidth - 2 * pad
    return l
}

/// A full-width row that highlights on hover, like a menu item. Icons sit in a fixed 18pt column,
/// so every icon and title lines up with the text above.
final class RowButton: NSView {
    let onClick: () -> Void
    init(_ title: String, symbol: String, bold: Bool = false, _ onClick: @escaping () -> Void) {
        self.onClick = onClick
        super.init(frame: .zero)
        wantsLayer = true
        layer!.cornerRadius = 6
        let icon = NSImageView(image: NSImage(systemSymbolName: symbol, accessibilityDescription: nil)!)
        icon.contentTintColor = bold ? .labelColor : .secondaryLabelColor
        icon.symbolConfiguration = .init(pointSize: 13, weight: bold ? .semibold : .regular)
        let text = NSTextField(labelWithString: title)
        text.font = .systemFont(ofSize: 13, weight: bold ? .semibold : .regular)
        for v in [icon, text] { v.translatesAutoresizingMaskIntoConstraints = false; addSubview(v) }
        NSLayoutConstraint.activate([
            heightAnchor.constraint(equalToConstant: 28),
            widthAnchor.constraint(equalToConstant: cardWidth - 2 * pad),
            icon.leadingAnchor.constraint(equalTo: leadingAnchor),
            icon.widthAnchor.constraint(equalToConstant: 18),
            icon.centerYAnchor.constraint(equalTo: centerYAnchor),
            text.leadingAnchor.constraint(equalTo: icon.trailingAnchor, constant: 8),
            text.centerYAnchor.constraint(equalTo: centerYAnchor),
        ])
    }
    required init?(coder: NSCoder) { fatalError() }
    override func mouseUp(with e: NSEvent) { onClick() }
    override func updateTrackingAreas() {
        trackingAreas.forEach(removeTrackingArea)
        addTrackingArea(NSTrackingArea(rect: bounds, options: [.mouseEnteredAndExited, .activeAlways],
                                       owner: self, userInfo: nil))
    }
    override func mouseEntered(with e: NSEvent) { layer!.backgroundColor = NSColor.quaternaryLabelColor.cgColor }
    override func mouseExited(with e: NSEvent) { layer!.backgroundColor = nil }
}

final class App: NSObject, NSApplicationDelegate {
    let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    let popover = NSPopover()
    var seenRefusals = 0  // ponytail: in-memory only; the badge comes back after a relaunch

    func applicationDidFinishLaunching(_ note: Notification) {
        let args = CommandLine.arguments
        if let i = args.firstIndex(of: "--snapshot"), i + 1 < args.count {
            NSApp.appearance = NSAppearance(named: .darkAqua)
            let v = card()
            v.wantsLayer = true
            v.layer!.backgroundColor = NSColor(white: 0.16, alpha: 1).cgColor  // like the dark popover
            let rep = v.bitmapImageRepForCachingDisplay(in: v.bounds)!
            v.cacheDisplay(in: v.bounds, to: rep)
            try? rep.representation(using: .png, properties: [:])?.write(to: URL(fileURLWithPath: args[i + 1]))
            exit(0)
        }
        item.button?.target = self
        item.button?.action = #selector(togglePopover)
        popover.behavior = .transient
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

    /// The card: on or off and since when, what happened, what needs you, then actions.
    func card() -> NSView {
        let run = lastRun()
        let stack = NSStackView()
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 4
        stack.edgeInsets = NSEdgeInsets(top: pad, left: pad, bottom: pad - 4, right: pad)
        func gap(_ n: CGFloat) { stack.setCustomSpacing(n, after: stack.arrangedSubviews.last!) }
        let w = cardWidth - 2 * pad

        var since = ""
        if isOn, let s = try? String(contentsOfFile: flagPath, encoding: .utf8) {
            let parts = s.split(separator: "\n", omittingEmptySubsequences: false)
            let oneChat = parts.count > 1 && !parts[1].trimmingCharacters(in: .whitespaces).isEmpty
            since = "Since \(parts[0]), \(oneChat ? "for one chat" : "for all chats")"
        }
        let dot = NSView()
        dot.wantsLayer = true
        dot.layer!.backgroundColor = (isOn ? NSColor.systemIndigo : NSColor.tertiaryLabelColor).cgColor
        dot.layer!.cornerRadius = 4
        dot.widthAnchor.constraint(equalToConstant: 8).isActive = true
        dot.heightAnchor.constraint(equalToConstant: 8).isActive = true
        let head = NSStackView(views: [dot, label(isOn ? "AWAY IS ON" : "AWAY IS OFF", 11, .semibold, .secondaryLabelColor)])
        head.spacing = 6
        stack.addArrangedSubview(head)
        gap(4)
        let busy = run.approved + run.answered + run.refused.count > 0
        stack.addArrangedSubview(label(isOn ? "Claude is working for you" : busy ? "Last time you were away" : "Claude waits for you",
                                       20, .bold))
        if isOn { stack.addArrangedSubview(label(since, 12, .regular, .secondaryLabelColor)) }
        gap(10)
        if busy {
            stack.addArrangedSubview(label("\(run.approved) approved · \(run.answered) answered for you", 13))
        } else if !isOn {
            stack.addArrangedSubview(label("Turn it on before you sleep or step out. Normal work goes ahead; anything risky waits for you.",
                                           12, .regular, .secondaryLabelColor))
        }
        if !run.refused.isEmpty {
            gap(10)
            stack.addArrangedSubview(label("Needs you (\(run.refused.count))", 13, .semibold, .systemOrange))
            for r in run.refused.prefix(5) {
                let one = NSTextField(labelWithString: "• \(r)")  // one line each, so the list scans
                one.font = .systemFont(ofSize: 12)
                one.textColor = .secondaryLabelColor
                one.lineBreakMode = .byTruncatingTail
                one.toolTip = r
                one.widthAnchor.constraint(equalToConstant: cardWidth - 2 * pad).isActive = true
                stack.addArrangedSubview(one)
            }
            if run.refused.count > 5 {
                stack.addArrangedSubview(label("+ \(run.refused.count - 5) more in the full report", 12, .regular, .tertiaryLabelColor))
            }
        }
        gap(12)
        let line = NSBox()
        line.boxType = .separator
        line.widthAnchor.constraint(equalToConstant: w).isActive = true
        stack.addArrangedSubview(line)
        gap(6)
        let rows = NSStackView(views: [
            RowButton(isOn ? "Turn off (I'm in)" : "Turn on for all chats", symbol: isOn ? "sun.max" : "moon.fill",
                      bold: true) { [weak self] in self?.toggle() },
            RowButton("Open full report", symbol: "doc.text") { [weak self] in self?.openReport() },
            RowButton(SMAppService.mainApp.status == .enabled ? "Opens at login  ✓" : "Open at login",
                      symbol: "power") { [weak self] in self?.toggleLogin() },
            RowButton("Quit Away", symbol: "xmark.circle") { NSApp.terminate(nil) },
        ])
        rows.orientation = .vertical
        rows.alignment = .leading
        rows.spacing = 0
        stack.addArrangedSubview(rows)
        gap(8)
        let credit = NSButton(title: "Made with ♥ by Purvang Mehta", target: self, action: #selector(openSite))
        credit.isBordered = false
        credit.font = .systemFont(ofSize: 11, weight: .medium)
        credit.contentTintColor = .secondaryLabelColor
        credit.toolTip = "thepurvangmehta.com"
        stack.addArrangedSubview(credit)
        stack.widthAnchor.constraint(equalToConstant: cardWidth).isActive = true
        stack.layoutSubtreeIfNeeded()
        stack.frame = NSRect(x: 0, y: 0, width: cardWidth, height: stack.fittingSize.height)
        return stack
    }

    @objc func togglePopover() {
        if popover.isShown { popover.performClose(nil); return }
        guard let button = item.button else { return }
        seenRefusals = lastRun().refused.count  // opening the card clears the badge
        refresh()
        let vc = NSViewController()
        vc.view = card()
        popover.contentViewController = vc
        popover.contentSize = vc.view.frame.size
        popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
        popover.contentViewController?.view.window?.makeKey()
    }

    func toggle() {
        popover.performClose(nil)
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

    func openReport() {
        popover.performClose(nil)
        if !FileManager.default.fileExists(atPath: logPath) { FileManager.default.createFile(atPath: logPath, contents: nil) }
        NSWorkspace.shared.open(URL(fileURLWithPath: logPath))
    }

    @objc func openSite() {
        popover.performClose(nil)
        NSWorkspace.shared.open(URL(string: "https://thepurvangmehta.com/?utm_source=away&utm_medium=app")!)
    }

    func toggleLogin() {
        let s = SMAppService.mainApp
        try? (s.status == .enabled ? s.unregister() : s.register())
        popover.performClose(nil)
    }
}

let app = NSApplication.shared
let delegate = App()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
