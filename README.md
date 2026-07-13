# stash

## Live daemon

Run stash in daemon mode to render template changes without creating generations:

```console
stash --dotfiles ~/.dotfiles daemon
```

Live files are written to `~/.local/share/stash/live/<module>/`, and deployed
symlinks point there while the daemon is running. Changes to `config.yaml` and
files in configured modules trigger a complete live render. Template or config
errors leave the previous live configuration active.

The daemon owns `org.dotstash.Stash` on the user session bus. Its initial
versioned interface supports health checks, explicit reloads, theme changes,
and graceful stops:

```console
busctl --user call org.dotstash.Stash /org/dotstash/Stash org.dotstash.Stash1 Ping
busctl --user call org.dotstash.Stash /org/dotstash/Stash org.dotstash.Stash1 Reload
busctl --user call org.dotstash.Stash /org/dotstash/Stash org.dotstash.Stash1 SetTheme s dark
busctl --user call org.dotstash.Stash /org/dotstash/Stash org.dotstash.Stash1 Stop
```

Themes use the Base16 color names. `theme` selects the initial theme, while a
`SetTheme` call changes it for the lifetime of the daemon:

```yaml
theme: dark
themes:
  dark:
    base00: "181818"
    base01: "282828"
    base02: "383838"
    base03: "585858"
    base04: "b8b8b8"
    base05: "d8d8d8"
    base06: "e8e8e8"
    base07: "f8f8f8"
    base08: "ab4642"
    base09: "dc9656"
    base0A: "f7ca88"
    base0B: "a1b56c"
    base0C: "86c1b9"
    base0D: "7cafc2"
    base0E: "ba8baf"
    base0F: "a16946"
```

The selected mapping remains available to templates as `colors`, so existing
references such as `{{ colors.base01 }}` continue to work. The old `colors`
configuration mapping is no longer accepted.

### Adopting files

Copy existing files into a new module with:

```console
stash --dotfiles ~/.dotfiles adopt ~/.vimrc
```

The command records the files' original parent directory as the module target
in `config.yaml`. It does not render or deploy files itself; the running daemon
notices the new module and updates the target symlinks.

### Hooks

D-Bus methods trigger pre- and post-hooks named after the kebab-case method
name. Hooks live under `hooks/` by default and run in lexical order using
systemd-style drop-in names:

```text
hooks/
  pre-reload.d/
    10-notify.sh
  pre-set-theme.d/
    10-prepare.sh
  post-set-theme.d/
    10-terminal.sh
    20-editor.py
```

Set a different location within the dotfiles repository with `hooks_dir`:

```yaml
hooks_dir: scripts/hooks
```

Files must match `[0-9]{2}-<name>.sh` or `[0-9]{2}-<name>.py`. They are rendered
as Jinja templates with the normal stash variables plus `event` and
`arguments`. Hook processes also receive `STASH_EVENT`, JSON-encoded
`STASH_ARGUMENTS`, and variables such as `STASH_ARG_NAME`. Shell hooks run with
`/bin/sh`; Python hooks use the same Python environment as stash. Each hook has
a hard one-second timeout. A failing or timed-out pre-hook prevents the method
from running. A failing or timed-out post-hook is reported after the method has
completed. For `SetTheme`, pre-hooks see the old theme and post-hooks see the
newly rendered theme, allowing them to reload applications.

Live symlinks remain valid when the daemon stops because the render tree is
persistent. The next daemon start updates them atomically.

Install and start a rendered systemd user service with:

```console
stash --dotfiles ~/.dotfiles systemd-install
```

The command writes `~/.config/systemd/user/stash.service`, reloads the user
systemd manager, enables the service, and starts or restarts it. The unit uses
the current Python environment and resolved config and dotfiles paths. Inspect
it with `systemctl --user cat stash.service` and follow its output with
`journalctl --user -u stash.service -f`.
