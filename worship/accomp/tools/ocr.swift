// 맥 Vision 글자 인식 — 그림 파일들을 받아 한 줄에 하나씩 JSON 으로 낸다 (곡별 PPT 제목 읽기용).
// swift accomp/tools/ocr.swift a.png b.png …  →  {"file":…, "lines":[{"t":…,"x":…,"y":…,"h":…}]}
import Foundation
import Vision
import AppKit

for path in CommandLine.arguments.dropFirst() {
    guard let img = NSImage(contentsOfFile: path),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { continue }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.recognitionLanguages = ["ko-KR", "en-US"]
    req.usesLanguageCorrection = false
    try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
    var lines: [[String: Any]] = []
    for o in req.results ?? [] {
        guard let c = o.topCandidates(1).first else { continue }
        let b = o.boundingBox
        lines.append(["t": c.string, "x": b.minX, "y": 1 - b.maxY, "w": b.width, "h": b.height])
    }
    let d = try! JSONSerialization.data(withJSONObject: ["file": path, "lines": lines])
    print(String(data: d, encoding: .utf8)!)
}
