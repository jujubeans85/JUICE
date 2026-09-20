# READ THIS — Mum iOS capability

Status: **APPROVED / queued for implementation**

Owner surface: **MA phone**
Shared engine: **JUICE Reader**
Target: **iPhone, local-first**

## Outcome

Mum gets one obvious **READ THIS** control. It reads ordinary visible text aloud without asking her to understand OCR, sharing, files, voices, or AI.

This is a capability underneath the existing MA interface, not a separate app or a second reading system.

## Jobs

1. **Read what is already on the phone**
   - Message, webpage, PDF, email, or a photo Adam has sent.
   - Preferred path: the native iOS accessibility reading action when the current app exposes text.
   - Fallback path: capture/share an image, recognise text locally, then speak it.

2. **Read a physical item**
   - Letter, newspaper, bill, appointment sheet, label, or medicine instructions.
   - Take/select photo → recognise text → speak it.

## Mum interface

Idle:

- One large blue **READ THIS** button.
- No setup choices.

Speaking:

- One large **STOP** button.
- One secondary **AGAIN** button.

Errors must be plain and spoken where possible:

- “I can’t find writing. Try moving closer.”
- “That photo is blurry. Take another photo.”
- “Nothing to read on this screen.”

No login, account, prompt box, file browser, model picker, voice picker, or settings maze in Mum mode.

## Architecture

```
MA launcher / iOS Shortcut
        ↓
Capture adapter
  ├─ current accessible screen text
  ├─ shared image / screenshot
  └─ camera / photo picker
        ↓
Local text recognition
        ↓
JUICE Reader speech controller
        ↓
STOP / AGAIN
```

The capture adapter is iOS-specific. Text cleanup, passage segmentation, speech state, cancellation, replay, and receipts should stay reusable in JUICE Reader.

Do not duplicate a second speech engine inside the MA launcher.

## Privacy and resilience

- Local-first OCR and on-device speech where iOS supports them.
- No document upload required for normal reading.
- No analytics.
- Do not retain recognised text or photos after the reading session unless Adam deliberately saves them.
- Ordinary reading must work without a JUICE Control server.
- If an installed voice needs network access, label that honestly during setup; Mum should never have to decide at runtime.

## iOS delivery surfaces

Ship the same semantic action through the smallest useful surfaces:

- MA home-screen button: **READ THIS**
- Share Sheet action for photos, PDFs, webpages, and messages
- Optional Back Tap / Action Button binding for reading the current screen
- Camera/photo intake inside the shortcut or native companion

The exact current-screen implementation needs a physical-iPhone spike because iOS limits cross-app screen access. Do not claim a universal one-tap screen scraper. Prefer native accessibility reading when available; otherwise use an explicit screenshot/share fallback.

## Acceptance gates

- [ ] Mum can start it from one familiar button.
- [ ] A photo of a newspaper can be read aloud.
- [ ] A received image in Messages can be shared into it and read aloud.
- [ ] Ordinary selectable text on screen can be read through the native accessibility path.
- [ ] STOP halts speech immediately.
- [ ] AGAIN repeats the last successful reading.
- [ ] Empty, angled, dark, and blurry captures produce a simple recovery instruction.
- [ ] No sign-in or cloud service is required for the normal path.
- [ ] No captured document persists after the session by default.
- [ ] VoiceOver, Dynamic Type, high contrast, and large touch targets remain usable.
- [ ] Tested on Mum’s actual iPhone; simulator success alone does not close the gate.

## Build order

1. Physical-device spike: native current-screen accessibility action versus screenshot fallback.
2. Share Sheet image/PDF intake.
3. Camera/photo OCR intake.
4. Reuse Reader speech/STOP/AGAIN state.
5. Add the single MA launcher control.
6. Run the acceptance gates with Mum.

## Non-goals for v1

- Summarising or explaining documents.
- Translating.
- Saving an archive.
- General AI chat.
- A fancy scanner interface.
