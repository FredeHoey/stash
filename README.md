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

On `SIGINT` or `SIGTERM`, stash restores each affected module's symlinks to its
latest stored generation.

Install and start a rendered systemd user service with:

```console
stash --dotfiles ~/.dotfiles systemd-install
```

The command writes `~/.config/systemd/user/stash.service`, reloads the user
systemd manager, enables the service, and starts or restarts it. The unit uses
the current Python environment and resolved config and dotfiles paths. Inspect
it with `systemctl --user cat stash.service` and follow its output with
`journalctl --user -u stash.service -f`.
