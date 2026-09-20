# READ THIS — Mum iOS capability

Status: **APPROVED / revised scope / queued for device validation**
Owner: **MA phone**. Reusable reading capability, not a separate app.
Updated: 2026-09-20.

## Expert brief

Simplify reading to: Mum opens the content, invokes one familiar reading control, and listens. Remove taking photos, camera access, photo picking and physical-document scanning entirely from this feature.

## Scope

- Read the message, webpage, email or document already open.
- Keep text in a received image already open on screen as a desired use case; this is NOT a camera/photo-picker workflow.
- No importing, copying, sharing, manual screenshots or choosing input modes in Mum's normal flow.
- No camera permissions or instructions to take another photo.
- No login, prompt box, model picker or voice settings during use.

## Recommended first implementation

Start with native iOS Speak Screen and its persistent on-screen controller. Configure it once with Adam, on Mum's actual iPhone. This keeps her in the content instead of sending her Home to press a launcher icon, losing the screen she wanted read.

Target experience: open content → familiar reading control → listen; obvious pause/stop.
Measure actual taps and control visibility. Do not claim the native controller is a custom blue READ THIS button or guarantees single-tap start. Select the simplest repeatable configuration Mum can independently use.

Apple documents Speak Screen, Show Controller and playback controls:
https://support.apple.com/guide/iphone/hear-whats-on-the-screen-or-typed-iph96b214f0/ios

Exact settings, control actions and suitability must be verified against her installed iOS version.

## Received-image boundary

Test a received image opened in Messages separately from ordinary text. Native screen reading must not be assumed to perform reliable OCR in every app.

If native support fails, investigate user-triggered, temporary current-screen capture plus local OCR behind the same simple control, without camera, photo picker, manual screenshot or Share Sheet steps for Mum. This is a feasibility investigation, not shipped functionality or guaranteed cross-app access. Never silently read the latest photo, clipboard or unrelated content.

If no equally simple reliable image path is possible, record that gate as unsupported/pending and explain it to Adam. Do not reintroduce a scanner workflow. As a practical sender-side accommodation, Adam can send the article text alongside its picture.

## Shared architecture

READ THIS remains a capability beneath the MA system. Use a platform adapter: iOS owns native Speak Screen playback; JUICE Reader owns playback for text actually delivered into Reader. Reuse Reader's existing text/speech state where applicable, with no duplicate custom engine.

Do not force native iOS speech through a browser or imply JUICE Reader can control Apple's system speech session. Only one speech owner per reading session. Preserve existing Reader behavior.

## Controls and recovery

- Read and an obvious way to silence playback are essential.
- AGAIN is optional; defer it if it adds a menu or competing control.
- Caregiver configures voice/rate once; no choices during normal use.
- Plain failure message where the chosen implementation permits it: “I can't read this screen.”
- Never direct Mum to take a photo, scan, import or navigate a file picker.

## Privacy and resilience

Local-first, no account, analytics or normal document uploads. No Mac/Control server dependency. Test offline with installed voices. Any custom temporary screen image/text must be discarded after the session; do not alter original received images/messages. No continuous screen monitoring.

## Acceptance gates

- [ ] Record Mum's iPhone model, installed iOS and chosen configuration.
- [ ] She can invoke reading without leaving the content or needing coaching.
- [ ] Messages text, an article and a text PDF tested individually.
- [ ] Received-image text tested separately; report supported versus pending honestly.
- [ ] She can silence speech immediately and reliably.
- [ ] No camera, photo picker, import, manual screenshot or sharing step.
- [ ] Controls are legible, easy to hit and do not obscure required content.
- [ ] Offline voice test passes; playback is audible through intended output.
- [ ] No new retained document data in any custom path.
- [ ] Unreadable content fails safely without invented text.
- [ ] Physical-device evidence required; not complete until Mum can use it.

## Work order

1. Configure/test native Speak Screen controller on Mum's phone.
2. Check independent start/stop usability and ordinary-text cases.
3. Validate received images; investigate invisible-to-Mum OCR only if needed and feasible.
4. Add custom code only for an evidenced gap. Reuse existing Reader components where relevant.
5. Record exact supported cases and remaining limits.

## Removed from scope

Taking photos, camera/photo-picker intake, physical-document scanning, Share Sheet onboarding for Mum, multiple launch gestures to learn, and a separate scanner UI. No summarisation, translation, archive or chat.
