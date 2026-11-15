# Use the same Music Door on iPhone and iPad

The phone opens the music page served by the existing JC process. The GPU engine
and JC must remain running, but Safari does not have to remain open after a take
has been accepted. The phone does not run the model.

These instructions prepare a private connection. They have not been applied to
the live Mac or a physical iPhone. First identify which checkout actually owns
the running JC, including the previously reported 8765/8780 distinction. Keep
the existing data root and preserve the currently working installation.

## Private access with Tailscale Serve

Use the normal Tailscale app on the Mac and iPhone, signed into the intended
account, with approved devices. The app's server remains bound to `127.0.0.1`.
The phone should be an ordinary user-owned device, not a tagged service device.

1. On the JC host, inspect `tailscale serve status`. Preserve any existing Serve
   routes; do not reset them or replace another root service.
2. If the host's HTTPS root has no conflicting service, run:

   ```sh
   tailscale serve --bg --https=443 http://127.0.0.1:8765
   ```

   Substitute the **verified JC port** if it differs. This command may first
   request HTTPS-certificate setup. Use Serve, not public Funnel.
3. Copy the actual private HTTPS origin printed by Tailscale. Set these values in
   the environment of the existing JC launcher, using your real values:

   ```sh
   export JUICE_MUSIC_PRIVATE_ORIGIN='https://your-actual-host.your-tailnet.ts.net'
   export JUICE_MUSIC_TAILSCALE_LOGIN='your-actual-tailscale-login'
   ```

   The origin must have no `/music/` path. Do not reuse the example hostname or
   assume the login from a profile name. Use the exact Tailscale account login.
4. Restart the identified JC process through its normal launcher so those
   environment values reach it. Do not start a competing JC process.
5. With Tailscale connected on iPhone, open the actual private origin followed
   by `/music/` in Safari. Choose **Share → Add to Home Screen**.

Serve's `--bg` option preserves the proxy configuration. It does not launch or
supervise JC or ComfyUI. Keep the computer awake for rendering and playback.

The application verifies the exact private hostname, HTTPS proxy marker and
Tailscale user login. It rejects missing or mismatched identity. This remote
route serves only Music and its API; legacy JC folder-opening and diagnostics
routes remain unavailable remotely. The root URL redirects to Music.

Tailscale removes incoming identity headers and supplies the authenticated
requester's identity. The app relies on this property and on the backend staying
on loopback. Do not point an arbitrary public reverse proxy at this interface or
add guessed identity headers to make requests pass.

Keep access restricted to the intended account and host in the tailnet's grants
or ACLs. A tailnet can otherwise permit other members to connect. Grants are
additive; a narrow new grant does not cancel an older broad grant. The app also
checks the exact account login as a second boundary.

To remove only the root HTTPS proxy described above, after checking its current
configuration:

```sh
tailscale serve --https=443 off
```

Do not run that command if it would remove another service you still need.
Removing the two `JUICE_MUSIC_*` access settings and restarting JC disables its
private remote entry without changing stored takes.

## What works offline

After a successful first visit over HTTPS, the home-screen app can retain its
static interface. Your current unsent draft is saved on that device and can be
exported as JSON. Project history and recordings stay in JC. The service worker
never caches API responses or audio, and there is no hidden background upload.

When returning to an active take, the app refreshes the original job. If JC lost
contact with a known engine job, **Check original result** retrieves that same
result without starting another generation. An ambiguous submission without an
engine receipt needs inspection in ComfyUI before generating again.

## First physical-device check

Open a completed MP3 in Safari, seek forward, download the FLAC, then add the
page to the Home Screen and reopen it. Check that its history matches desktop JC.
Test one short generation, leave Safari, and return to the same take. File sharing
depends on browser support; the Download action is the fallback through Files.

The implementation includes byte-range and HEAD responses for audio seeking,
PNG home-screen icons, 16px inputs and safe-area spacing. Physical Safari and
private network acceptance remain deployment checks, not completed claims.

## Official references

- [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve)
- [Serve CLI](https://tailscale.com/kb/1242/tailscale-serve)
- [Identity headers](https://tailscale.com/docs/features/tailscale-serve#identity-headers)
- [Access-control grants](https://tailscale.com/kb/1324/grants)
- [Tailscale proxy implementation](https://github.com/tailscale/tailscale/blob/main/ipn/ipnlocal/serve.go)
