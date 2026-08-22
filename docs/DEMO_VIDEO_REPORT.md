# Demo Video Report

Status: **LOCAL MEDIA VERIFIED / LIVE MINDS CONTINUITY VERIFIED**

## Final local artifact

- File: `output/demo-video/cohortloom-demo.mp4`
- Rendered: 2026-08-22 (Asia/Shanghai task date)
- Duration: `111.000` seconds
- Resolution: `1920x1080`
- Frame rate: `30.000 fps`
- Video codec: H.264 (`avc1`)
- Video tracks: `1`
- Audio tracks: `1`
- Narration track duration: `111.000` seconds
- File size: `24,704,292` bytes
- SHA-256: `2acde0be3a1661649c06c38ceabd3a1fa65403963203f14b4073e2c5c420bade`

## Truth label

The current deterministic render displays both:

- `SYNTHETIC DEMO`
- `LIVE MINDS CONTINUITY VERIFIED`

The generator switched the second label to `LIVE MINDS CONTINUITY VERIFIED` only after
`output/live_minds_evidence.json` passes strict checks for one store, one plan recall, one
due-review recall, three distinct conversations, the same Mind, and three schema-valid calls.
It never removes the synthetic-data label.

## Commands

```bash
uv run python scripts/generate_demo_video_assets.py
swift scripts/render_demo_video.swift \
  output/demo-video/scene_manifest.json \
  output/demo-video/narration.aiff \
  output/demo-video/cohortloom-silent.mov \
  output/demo-video/cohortloom-demo.mp4
swift scripts/verify_demo_video.swift \
  output/demo-video/cohortloom-demo.mp4 \
  output/demo-video/preview-midpoint.png 55.5
```

The verifier returned `MEDIA_VERIFY_OK`. A midpoint frame was inspected locally; the
three-session diagram, synthetic label, verified-live label, and narration were legible.

## Evidence boundary

The MP4 is structurally valid and its verified-live label is gated by the separate redacted
Minds evidence artifact. The video still does not prove public upload, real users, revenue,
creator adoption, or growth results. Public submission was not performed in this repository task.
