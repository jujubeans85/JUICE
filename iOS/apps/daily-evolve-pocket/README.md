# Daily Evolve Pocket · Crate Juice

[Open/share splash page](https://jujubeans85.github.io/ios/daily-evolve-pocket/) · [Open player](https://daily-evolve-pocket.xntfsstt5z.chatgpt.site/)

One track. Infinite rooms.

Independent iOS edition: daily date-seeded audio treatments, original comparison, archive, local favourites, listening achievements and WAV export. Add the player to Home Screen from Safari.

## Source of truth

- Player: Sites project `appgprj_6abbc49c2b248191b3ee834248a21dfa`.
- Splash and SVG: `jujubeans85/jujubeans85.github.io/ios/daily-evolve-pocket/`.
- This directory is the app catalog entry, not a second player implementation. Mac edition stays separate.
- App sharing carries `?day=YYYY-MM-DD` through the splash to the original player.

## Sharing

Send the splash URL through iMessage, not the raw SVG. The public splash uses SVG for its clickable card and a PNG rendering for social-preview metadata. Actual iMessage preview rendering needs a device check.

The player remains owner-private. A recipient can see the splash but cannot listen unless granted player access. The link does not grant access. Manage viewers through the original Site sharing settings.

No background AI or push service. Reminders use imported calendar entries; favourites remain device-local. Haptics depend on browser support.
