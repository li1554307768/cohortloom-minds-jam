#!/usr/bin/env swift

import AppKit
import AVFoundation
import CoreGraphics
import CoreVideo
import Foundation

struct Manifest: Decodable {
    let schemaVersion: String
    let brand: String
    let datasetLabel: String
    let liveEvidenceLabel: String
    let width: Int
    let height: Int
    let fps: Int32
    let duration: Double
    let scenes: [Scene]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case brand
        case datasetLabel = "dataset_label"
        case liveEvidenceLabel = "live_evidence_label"
        case width, height, fps, duration, scenes
    }
}

struct Scene: Decodable {
    let duration: Double
    let style: String
    let eyebrow: String
    let title: String
    let subtitle: String
}

enum RenderError: Error, CustomStringConvertible {
    case usage
    case invalidManifest(String)
    case pixelBuffer(String)
    case writer(String)
    case missingTrack(String)
    case export(String)

    var description: String {
        switch self {
        case .usage:
            return "Usage: render_demo_video.swift MANIFEST NARRATION SILENT_MOV FINAL_MP4"
        case .invalidManifest(let message), .pixelBuffer(let message), .writer(let message),
             .missingTrack(let message), .export(let message):
            return message
        }
    }
}

let backgroundTop = NSColor(calibratedRed: 0.055, green: 0.047, blue: 0.105, alpha: 1)
let backgroundBottom = NSColor(calibratedRed: 0.102, green: 0.071, blue: 0.157, alpha: 1)
let surface = NSColor(calibratedRed: 0.105, green: 0.094, blue: 0.165, alpha: 1)
let surfaceRaised = NSColor(calibratedRed: 0.143, green: 0.122, blue: 0.215, alpha: 1)
let border = NSColor(calibratedRed: 0.294, green: 0.259, blue: 0.404, alpha: 1)
let ivory = NSColor(calibratedRed: 0.975, green: 0.961, blue: 0.925, alpha: 1)
let muted = NSColor(calibratedRed: 0.719, green: 0.690, blue: 0.765, alpha: 1)
let pink = NSColor(calibratedRed: 0.957, green: 0.447, blue: 0.714, alpha: 1)
let violet = NSColor(calibratedRed: 0.655, green: 0.545, blue: 0.980, alpha: 1)
let teal = NSColor(calibratedRed: 0.176, green: 0.831, blue: 0.749, alpha: 1)
let amber = NSColor(calibratedRed: 0.984, green: 0.749, blue: 0.141, alpha: 1)
let red = NSColor(calibratedRed: 0.984, green: 0.353, blue: 0.420, alpha: 1)

func paragraph(alignment: NSTextAlignment = .left, lineBreak: NSLineBreakMode = .byWordWrapping) -> NSMutableParagraphStyle {
    let style = NSMutableParagraphStyle()
    style.alignment = alignment
    style.lineBreakMode = lineBreak
    style.lineSpacing = 4
    return style
}

func drawText(
    _ text: String,
    in rect: NSRect,
    size: CGFloat,
    color: NSColor = ivory,
    weight: NSFont.Weight = .regular,
    alignment: NSTextAlignment = .left,
    lineBreak: NSLineBreakMode = .byWordWrapping
) {
    let attributes: [NSAttributedString.Key: Any] = [
        .font: NSFont.systemFont(ofSize: size, weight: weight),
        .foregroundColor: color,
        .paragraphStyle: paragraph(alignment: alignment, lineBreak: lineBreak),
    ]
    (text as NSString).draw(in: rect, withAttributes: attributes)
}

func roundedRect(
    _ rect: NSRect,
    radius: CGFloat,
    fill: NSColor,
    stroke: NSColor? = nil,
    width: CGFloat = 1
) {
    let path = NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius)
    fill.setFill()
    path.fill()
    if let stroke {
        stroke.setStroke()
        path.lineWidth = width
        path.stroke()
    }
}

func pill(_ rect: NSRect, text: String, color: NSColor, fillAlpha: CGFloat = 0.13) {
    roundedRect(rect, radius: rect.height / 2, fill: color.withAlphaComponent(fillAlpha), stroke: color, width: 2)
    drawText(text, in: NSRect(x: rect.minX + 12, y: rect.minY + 11, width: rect.width - 24, height: rect.height - 18), size: 18, color: color, weight: .bold, alignment: .center, lineBreak: .byTruncatingTail)
}

func card(_ rect: NSRect, title: String, body: String, accent: NSColor = violet, bodySize: CGFloat = 25) {
    roundedRect(rect, radius: 24, fill: surfaceRaised, stroke: border, width: 2)
    roundedRect(NSRect(x: rect.minX + 24, y: rect.minY + 24, width: 9, height: 46), radius: 4, fill: accent)
    drawText(title, in: NSRect(x: rect.minX + 54, y: rect.minY + 22, width: rect.width - 78, height: 54), size: 27, color: accent, weight: .semibold)
    drawText(body, in: NSRect(x: rect.minX + 30, y: rect.minY + 91, width: rect.width - 60, height: rect.height - 115), size: bodySize, color: ivory)
}

func line(from start: NSPoint, to end: NSPoint, color: NSColor, width: CGFloat = 4, dashed: Bool = false) {
    let path = NSBezierPath()
    path.move(to: start)
    path.line(to: end)
    path.lineWidth = width
    if dashed { path.setLineDash([12, 10], count: 2, phase: 0) }
    color.setStroke()
    path.stroke()
}

func arrow(from start: NSPoint, to end: NSPoint, color: NSColor) {
    line(from: start, to: end, color: color, width: 5)
    let angle = atan2(end.y - start.y, end.x - start.x)
    let wing: CGFloat = 17
    let left = NSPoint(x: end.x - wing * cos(angle - .pi / 6), y: end.y - wing * sin(angle - .pi / 6))
    let right = NSPoint(x: end.x - wing * cos(angle + .pi / 6), y: end.y - wing * sin(angle + .pi / 6))
    let head = NSBezierPath()
    head.move(to: end)
    head.line(to: left)
    head.line(to: right)
    head.close()
    color.setFill()
    head.fill()
}

func loomMark(center: NSPoint, scale: CGFloat = 1) {
    let size = 70 * scale
    let rect = NSRect(x: center.x - size / 2, y: center.y - size / 2, width: size, height: size)
    roundedRect(rect, radius: 18 * scale, fill: violet, stroke: pink, width: 3 * scale)
    roundedRect(NSRect(x: rect.minX + 17 * scale, y: rect.minY + 17 * scale, width: 36 * scale, height: 36 * scale), radius: 9 * scale, fill: backgroundTop)
    for offset in stride(from: CGFloat(8), through: size - 8, by: 12 * scale) {
        let dot = NSRect(x: rect.minX + offset - 2 * scale, y: rect.minY - 3 * scale, width: 4 * scale, height: 6 * scale)
        roundedRect(dot, radius: 2 * scale, fill: pink)
    }
}

func drawHeader(scene: Scene, manifest: Manifest, index: Int) {
    loomMark(center: NSPoint(x: 78, y: 67), scale: 0.62)
    drawText(manifest.brand.uppercased(), in: NSRect(x: 124, y: 42, width: 400, height: 42), size: 23, color: ivory, weight: .bold)
    pill(NSRect(x: 1510, y: 40, width: 330, height: 45), text: "SYNTHETIC DEMO", color: teal)
    drawText(scene.eyebrow, in: NSRect(x: 80, y: 112, width: 1500, height: 36), size: 21, color: pink, weight: .bold)
    drawText(scene.title, in: NSRect(x: 80, y: 153, width: 1690, height: 75), size: 48, color: ivory, weight: .bold)
    let progressWidth = 1760 * CGFloat(index + 1) / CGFloat(manifest.scenes.count)
    roundedRect(NSRect(x: 80, y: 1017, width: 1760, height: 5), radius: 2.5, fill: border)
    roundedRect(NSRect(x: 80, y: 1017, width: progressWidth, height: 5), radius: 2.5, fill: pink)
}

func drawSubtitle(_ text: String) {
    roundedRect(NSRect(x: 80, y: 833, width: 1760, height: 158), radius: 26, fill: NSColor(calibratedWhite: 0.035, alpha: 0.86), stroke: border, width: 2)
    drawText("NARRATION", in: NSRect(x: 116, y: 858, width: 200, height: 30), size: 17, color: teal, weight: .bold)
    drawText(text, in: NSRect(x: 116, y: 891, width: 1688, height: 80), size: 29, color: ivory, weight: .medium, alignment: .center)
}

func drawTitleScene() {
    loomMark(center: NSPoint(x: 960, y: 397), scale: 1.7)
    drawText("WEAVE SIGNALS INTO TESTS", in: NSRect(x: 250, y: 535, width: 1420, height: 86), size: 61, color: ivory, weight: .heavy, alignment: .center)
    drawText("Weekly metrics → falsifiable hypothesis → seven-day experiment → due review", in: NSRect(x: 260, y: 626, width: 1400, height: 55), size: 28, color: muted, weight: .medium, alignment: .center)
    pill(NSRect(x: 260, y: 714, width: 430, height: 55), text: "PERSISTENT HYPOTHESIS", color: violet)
    pill(NSRect(x: 745, y: 714, width: 430, height: 55), text: "SUCCESS + STOP", color: teal)
    pill(NSRect(x: 1230, y: 714, width: 430, height: 55), text: "NO OUTREACH", color: amber)
}

func drawBranchScene() {
    let cards: [(String, String, NSColor)] = [
        ("X", "42.8K views\n284 saves\n19 qualified replies", pink),
        ("LINKEDIN", "12.6K views\n219 saves\n27 qualified replies", violet),
        ("YOUTUBE", "9.1K views\n341 saves\n36 qualified replies", teal),
    ]
    for (index, item) in cards.enumerated() {
        card(NSRect(x: 100 + CGFloat(index) * 590, y: 300, width: 540, height: 390), title: item.0, body: item.1, accent: item.2, bodySize: 31)
        pill(NSRect(x: 180 + CGFloat(index) * 590, y: 725, width: 380, height: 52), text: "SYNTHETIC METRICS", color: item.2)
    }
}

func drawTruthScene() {
    card(NSRect(x: 100, y: 292, width: 520, height: 420), title: "OBSERVATION", body: "Practical teardown content earned stronger saves and substantive replies in one synthetic week.", accent: pink, bodySize: 29)
    arrow(from: NSPoint(x: 650, y: 500), to: NSPoint(x: 760, y: 500), color: violet)
    card(NSRect(x: 790, y: 292, width: 1020, height: 420), title: "FALSIFIABLE HYPOTHESIS", body: "Practical teardown posts activate quiet viewers better than broad motivational posts.\n\nRisk: small synthetic sample. Test for seven days before generalizing.", accent: violet, bodySize: 31)
    pill(NSRect(x: 615, y: 742, width: 690, height: 54), text: "HUMAN APPROVAL REQUIRED", color: amber)
}

func drawScanScene() {
    let steps = [
        ("01", "NORMALIZE", "Bound synthetic metrics", pink),
        ("02", "COMPARE", "Saves + qualified replies", violet),
        ("03", "FRAME", "Hypothesis + uncertainty", teal),
        ("04", "GATE", "Creator approval", amber),
    ]
    for (index, item) in steps.enumerated() {
        let x = 100 + CGFloat(index) * 440
        card(NSRect(x: x, y: 330, width: 390, height: 330), title: "\(item.0) • \(item.1)", body: item.2, accent: item.3, bodySize: 28)
        if index < steps.count - 1 { arrow(from: NSPoint(x: x + 400, y: 500), to: NSPoint(x: x + 430, y: 500), color: item.3) }
    }
    pill(NSRect(x: 575, y: 725, width: 770, height: 58), text: "DETERMINISTIC FIRST • 0 MODEL CALLS", color: teal)
}

func drawMemoryScene(liveLabel: String) {
    card(NSRect(x: 100, y: 298, width: 570, height: 390), title: "LOCAL + HUMAN", body: "Approved audience hypothesis\nEvidence basis\nRisk note\n\nNo voice or style profile", accent: teal, bodySize: 27)
    roundedRect(NSRect(x: 755, y: 385, width: 410, height: 210), radius: 28, fill: pink.withAlphaComponent(0.12), stroke: pink, width: 3)
    drawText("AUTHORIZED REQUEST", in: NSRect(x: 790, y: 420, width: 340, height: 42), size: 24, color: pink, weight: .bold, alignment: .center)
    drawText("isolated data\nmemory key\napproved hypothesis", in: NSRect(x: 805, y: 475, width: 310, height: 98), size: 23, color: ivory, alignment: .center)
    arrow(from: NSPoint(x: 690, y: 490), to: NSPoint(x: 735, y: 490), color: pink)
    arrow(from: NSPoint(x: 1185, y: 490), to: NSPoint(x: 1230, y: 490), color: pink)
    card(NSRect(x: 1250, y: 298, width: 570, height: 390), title: "MINDS", body: "Remember exactly:\nfalsifiable hypothesis\ncreator approval boundary\nexperiment continuity", accent: violet, bodySize: 25)
    pill(NSRect(x: 590, y: 730, width: 740, height: 54), text: liveLabel, color: amber)
}

func drawSessionsScene(liveLabel: String) {
    card(NSRect(x: 80, y: 300, width: 520, height: 370), title: "SESSION A • STORE", body: "Approved hypothesis\nEvidence + risk\nPrivate memory key", accent: teal, bodySize: 27)
    card(NSRect(x: 700, y: 300, width: 520, height: 370), title: "SESSION B • PLAN", body: "Prior hypothesis omitted\n7 manual days\nWHY NOW + success + stop", accent: violet, bodySize: 27)
    card(NSRect(x: 1320, y: 300, width: 520, height: 370), title: "SESSION C • REVIEW", body: "Local due check\nHypothesis omitted again\nCONTINUE / STOP / REVISE", accent: pink, bodySize: 27)
    arrow(from: NSPoint(x: 615, y: 488), to: NSPoint(x: 680, y: 488), color: pink)
    arrow(from: NSPoint(x: 1235, y: 488), to: NSPoint(x: 1300, y: 488), color: pink)
    pill(NSRect(x: 590, y: 730, width: 740, height: 54), text: liveLabel, color: amber)
}

func drawPlanScene() {
    for day in 1...7 {
        let column = (day - 1) % 4
        let row = (day - 1) / 4
        let x = 100 + CGFloat(column) * 440
        let y = 285 + CGFloat(row) * 225
        roundedRect(NSRect(x: x, y: y, width: 390, height: 185), radius: 22, fill: surfaceRaised, stroke: day == 7 ? amber : violet, width: 2)
        drawText("DAY \(day)", in: NSRect(x: x + 24, y: y + 24, width: 120, height: 38), size: 25, color: day == 7 ? amber : violet, weight: .bold)
        drawText(day == 7 ? "Review results against success and stop conditions" : "One bounded creator-owned action + human checkpoint", in: NSRect(x: x + 24, y: y + 72, width: 342, height: 80), size: 22, color: ivory)
    }
}

func drawReviewScene() {
    card(NSRect(x: 100, y: 285, width: 800, height: 455), title: "EXPERIMENT CONTRACT", body: "SUCCESS\n≥ 12 qualified replies\nSave rate ≥ 3%\n\nSTOP\n< 4 qualified replies\nNegative feedback > 5%", accent: teal, bodySize: 29)
    card(NSRect(x: 1020, y: 285, width: 800, height: 455), title: "DUE REVIEW", body: "Observed result:\nexperiment unfinished\nthreshold not reached\n\nRecommendation:\nREVISE\nHuman decides what happens next", accent: amber, bodySize: 29)
}

func drawPauseScene() {
    roundedRect(NSRect(x: 120, y: 310, width: 710, height: 360), radius: 40, fill: amber.withAlphaComponent(0.11), stroke: amber, width: 3)
    drawText("PAUSE", in: NSRect(x: 170, y: 365, width: 610, height: 60), size: 47, color: ivory, weight: .heavy, alignment: .center)
    roundedRect(NSRect(x: 255, y: 460, width: 440, height: 125), radius: 62, fill: amber)
    let knob = NSBezierPath(ovalIn: NSRect(x: 575, y: 475, width: 95, height: 95))
    ivory.setFill()
    knob.fill()
    drawText("ON", in: NSRect(x: 315, y: 497, width: 190, height: 46), size: 31, color: backgroundTop, weight: .heavy, alignment: .center)
    card(NSRect(x: 980, y: 310, width: 800, height: 360), title: "SAFETY CONTROLS", body: "0 automatic posts\n0 messages or follows\nBalance ≤ 10 → STOP\nUNCERTAIN → history check\nNo blind retry", accent: red, bodySize: 29)
    line(from: NSPoint(x: 1040, y: 370), to: NSPoint(x: 1710, y: 620), color: red, width: 10)
    line(from: NSPoint(x: 1710, y: 370), to: NSPoint(x: 1040, y: 620), color: red, width: 10)
}

func drawAuditScene() {
    let events: [(String, String, NSColor)] = [
        ("01", "WEEKLY METRICS", pink),
        ("02", "HYPOTHESIS APPROVAL", teal),
        ("03", "THREE MEMORY SESSIONS", violet),
        ("04", "RESULT + DUE REVIEW", amber),
    ]
    let y: CGFloat = 490
    line(from: NSPoint(x: 220, y: y), to: NSPoint(x: 1700, y: y), color: border, width: 7)
    for (index, event) in events.enumerated() {
        let x = 260 + CGFloat(index) * 460
        let circle = NSBezierPath(ovalIn: NSRect(x: x - 35, y: y - 35, width: 70, height: 70))
        event.2.setFill()
        circle.fill()
        drawText(event.0, in: NSRect(x: x - 28, y: y - 14, width: 56, height: 34), size: 20, color: backgroundTop, weight: .heavy, alignment: .center)
        roundedRect(NSRect(x: x - 165, y: 590, width: 330, height: 100), radius: 22, fill: surfaceRaised, stroke: event.2, width: 2)
        drawText(event.1, in: NSRect(x: x - 145, y: 622, width: 290, height: 46), size: 22, color: event.2, weight: .bold, alignment: .center)
    }
    pill(NSRect(x: 475, y: 286, width: 970, height: 62), text: "SYNTHETIC ≠ USER • PLAN ≠ EXECUTION", color: amber)
}

func drawCloseScene() {
    loomMark(center: NSPoint(x: 960, y: 400), scale: 1.9)
    drawText("COHORTLOOM", in: NSRect(x: 380, y: 548, width: 1160, height: 84), size: 72, color: ivory, weight: .heavy, alignment: .center)
    drawText("Persistent experiments. Human decisions.", in: NSRect(x: 430, y: 650, width: 1060, height: 56), size: 32, color: teal, weight: .semibold, alignment: .center)
    pill(NSRect(x: 540, y: 738, width: 840, height: 52), text: "AUDIENCE GROWTH • NO OUTREACH", color: pink)
}

func drawScene(_ scene: Scene, manifest: Manifest, index: Int) {
    let bounds = NSRect(x: 0, y: 0, width: manifest.width, height: manifest.height)
    if let gradient = NSGradient(colors: [backgroundTop, backgroundBottom]) {
        gradient.draw(in: bounds, angle: -90)
    } else {
        backgroundTop.setFill()
        bounds.fill()
    }
    roundedRect(NSRect(x: 34, y: 28, width: CGFloat(manifest.width) - 68, height: CGFloat(manifest.height) - 56), radius: 34, fill: NSColor.clear, stroke: border, width: 2)
    drawHeader(scene: scene, manifest: manifest, index: index)
    switch scene.style {
    case "title": drawTitleScene()
    case "branch": drawBranchScene()
    case "truth": drawTruthScene()
    case "scan": drawScanScene()
    case "memory": drawMemoryScene(liveLabel: manifest.liveEvidenceLabel)
    case "sessions": drawSessionsScene(liveLabel: manifest.liveEvidenceLabel)
    case "plan": drawPlanScene()
    case "review": drawReviewScene()
    case "pause": drawPauseScene()
    case "audit": drawAuditScene()
    case "close": drawCloseScene()
    default: break
    }
    drawSubtitle(scene.subtitle)
}

func pixelBuffer(scene: Scene, manifest: Manifest, index: Int) throws -> CVPixelBuffer {
    let attributes: [CFString: Any] = [
        kCVPixelBufferCGImageCompatibilityKey: true,
        kCVPixelBufferCGBitmapContextCompatibilityKey: true,
        kCVPixelBufferIOSurfacePropertiesKey: [:],
    ]
    var optionalBuffer: CVPixelBuffer?
    let status = CVPixelBufferCreate(
        kCFAllocatorDefault,
        manifest.width,
        manifest.height,
        kCVPixelFormatType_32BGRA,
        attributes as CFDictionary,
        &optionalBuffer
    )
    guard status == kCVReturnSuccess, let buffer = optionalBuffer else {
        throw RenderError.pixelBuffer("CVPixelBufferCreate failed with status \(status)")
    }
    CVPixelBufferLockBaseAddress(buffer, [])
    defer { CVPixelBufferUnlockBaseAddress(buffer, []) }
    guard let address = CVPixelBufferGetBaseAddress(buffer) else {
        throw RenderError.pixelBuffer("Pixel buffer has no base address")
    }
    let bitmapInfo = CGBitmapInfo.byteOrder32Little.rawValue | CGImageAlphaInfo.premultipliedFirst.rawValue
    guard let context = CGContext(
        data: address,
        width: manifest.width,
        height: manifest.height,
        bitsPerComponent: 8,
        bytesPerRow: CVPixelBufferGetBytesPerRow(buffer),
        space: CGColorSpaceCreateDeviceRGB(),
        bitmapInfo: bitmapInfo
    ) else {
        throw RenderError.pixelBuffer("Could not create bitmap drawing context")
    }
    // AVFoundation treats the first pixel-buffer row as the top of the frame while
    // Core Graphics starts at the lower-left. Flip once so our layout coordinates
    // and AppKit text both use a normal top-left origin in the encoded video.
    context.translateBy(x: 0, y: CGFloat(manifest.height))
    context.scaleBy(x: 1, y: -1)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(cgContext: context, flipped: true)
    drawScene(scene, manifest: manifest, index: index)
    NSGraphicsContext.current?.flushGraphics()
    NSGraphicsContext.restoreGraphicsState()
    return buffer
}

func renderSilentVideo(manifest: Manifest, outputURL: URL) throws {
    try? FileManager.default.removeItem(at: outputURL)
    let writer = try AVAssetWriter(outputURL: outputURL, fileType: .mov)
    let compression: [String: Any] = [
        AVVideoAverageBitRateKey: 5_800_000,
        AVVideoMaxKeyFrameIntervalKey: Int(manifest.fps * 2),
        AVVideoProfileLevelKey: AVVideoProfileLevelH264HighAutoLevel,
    ]
    let settings: [String: Any] = [
        AVVideoCodecKey: AVVideoCodecType.h264,
        AVVideoWidthKey: manifest.width,
        AVVideoHeightKey: manifest.height,
        AVVideoCompressionPropertiesKey: compression,
    ]
    let input = AVAssetWriterInput(mediaType: .video, outputSettings: settings)
    input.expectsMediaDataInRealTime = false
    let adaptor = AVAssetWriterInputPixelBufferAdaptor(
        assetWriterInput: input,
        sourcePixelBufferAttributes: [
            kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
            kCVPixelBufferWidthKey as String: manifest.width,
            kCVPixelBufferHeightKey as String: manifest.height,
        ]
    )
    guard writer.canAdd(input) else {
        throw RenderError.writer("AVAssetWriter cannot add the video input")
    }
    writer.add(input)
    guard writer.startWriting() else {
        throw RenderError.writer(writer.error?.localizedDescription ?? "Writer did not start")
    }
    writer.startSession(atSourceTime: .zero)

    var frameNumber: Int64 = 0
    for (index, scene) in manifest.scenes.enumerated() {
        guard scene.duration > 0 else {
            throw RenderError.invalidManifest("Every scene duration must be positive")
        }
        let buffer = try pixelBuffer(scene: scene, manifest: manifest, index: index)
        let frameCount = Int64((scene.duration * Double(manifest.fps)).rounded())
        for _ in 0..<frameCount {
            while !input.isReadyForMoreMediaData {
                if writer.status == .failed {
                    throw RenderError.writer(writer.error?.localizedDescription ?? "Writer failed")
                }
                Thread.sleep(forTimeInterval: 0.002)
            }
            let time = CMTime(value: frameNumber, timescale: manifest.fps)
            guard adaptor.append(buffer, withPresentationTime: time) else {
                throw RenderError.writer(writer.error?.localizedDescription ?? "Could not append frame")
            }
            frameNumber += 1
        }
    }
    input.markAsFinished()
    let semaphore = DispatchSemaphore(value: 0)
    writer.finishWriting { semaphore.signal() }
    semaphore.wait()
    guard writer.status == .completed else {
        throw RenderError.writer(writer.error?.localizedDescription ?? "Writer did not complete")
    }
}

func merge(videoURL: URL, narrationURL: URL, outputURL: URL) throws {
    try? FileManager.default.removeItem(at: outputURL)
    let videoAsset = AVURLAsset(url: videoURL)
    let audioAsset = AVURLAsset(url: narrationURL)
    guard let sourceVideo = videoAsset.tracks(withMediaType: .video).first else {
        throw RenderError.missingTrack("Silent render has no video track")
    }
    guard let sourceAudio = audioAsset.tracks(withMediaType: .audio).first else {
        throw RenderError.missingTrack("Narration has no audio track")
    }
    let composition = AVMutableComposition()
    guard let videoTrack = composition.addMutableTrack(withMediaType: .video, preferredTrackID: kCMPersistentTrackID_Invalid),
          let audioTrack = composition.addMutableTrack(withMediaType: .audio, preferredTrackID: kCMPersistentTrackID_Invalid) else {
        throw RenderError.missingTrack("Could not create composition tracks")
    }
    try videoTrack.insertTimeRange(CMTimeRange(start: .zero, duration: videoAsset.duration), of: sourceVideo, at: .zero)
    let audioDuration = CMTimeMinimum(audioAsset.duration, videoAsset.duration)
    try audioTrack.insertTimeRange(CMTimeRange(start: .zero, duration: audioDuration), of: sourceAudio, at: .zero)
    guard let exporter = AVAssetExportSession(asset: composition, presetName: AVAssetExportPreset1920x1080) else {
        throw RenderError.export("Could not create 1080p export session")
    }
    exporter.outputURL = outputURL
    exporter.outputFileType = .mp4
    exporter.shouldOptimizeForNetworkUse = true
    let semaphore = DispatchSemaphore(value: 0)
    exporter.exportAsynchronously { semaphore.signal() }
    semaphore.wait()
    guard exporter.status == .completed else {
        throw RenderError.export(exporter.error?.localizedDescription ?? "Export did not complete")
    }
}

do {
    guard CommandLine.arguments.count == 5 else { throw RenderError.usage }
    let manifestURL = URL(fileURLWithPath: CommandLine.arguments[1])
    let narrationURL = URL(fileURLWithPath: CommandLine.arguments[2])
    let silentURL = URL(fileURLWithPath: CommandLine.arguments[3])
    let outputURL = URL(fileURLWithPath: CommandLine.arguments[4])
    let data = try Data(contentsOf: manifestURL)
    let manifest = try JSONDecoder().decode(Manifest.self, from: data)
    guard manifest.schemaVersion == "1.0", manifest.width == 1920, manifest.height == 1080,
          manifest.fps == 30, !manifest.scenes.isEmpty else {
        throw RenderError.invalidManifest("Manifest must be schema 1.0, 1920x1080, 30 fps and non-empty")
    }
    let summedDuration = manifest.scenes.reduce(0) { $0 + $1.duration }
    guard abs(summedDuration - manifest.duration) < 0.01,
          manifest.duration >= 105, manifest.duration <= 115 else {
        throw RenderError.invalidManifest("Manifest duration must be 105–115 seconds and match its scenes")
    }
    try renderSilentVideo(manifest: manifest, outputURL: silentURL)
    try merge(videoURL: silentURL, narrationURL: narrationURL, outputURL: outputURL)
    print("rendered=\(outputURL.path)")
} catch {
    FileHandle.standardError.write(Data("RENDER_FAIL: \(error)\n".utf8))
    exit(1)
}
