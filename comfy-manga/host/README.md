# manga-gpu (host helper)

The app container cannot touch Docker or the GPU stack itself. `manga-gpu` is the only command its SSH key may
run on the PC (forced command), with fixed verbs: `status`, `llm-mode` (stop comfyui-manga, llm-up),
`draw-mode` (llm-down, start comfyui-manga), `models`, `chat`, `unload` (relay to the llama.cpp router, which
listens on the host's 127.0.0.1:11434 only).

Install (done 2026-10-24 on laanta-chy):
- `ln -s ~/Others/P_projects/comfy-manga/host/manga-gpu ~/.local/bin/manga-gpu`
- key: `~/.config/manga-gpu/id_ed25519` (+ `known_hosts` with this PC's host key as `host.docker.internal`),
  mounted read-only at `/keys` in manga-app. Never in git.
- `~/.ssh/authorized_keys`: `restrict,from="172.16.0.0/12",command="/home/sgkayast/.local/bin/manga-gpu" ssh-ed25519 … manga-app@laanta-chy`
  (backup before the change: `~/.ssh/authorized_keys.bak-20261024-mangagpu`).

Remove: delete that authorized_keys line, the symlink and `~/.config/manga-gpu`, and the `/keys` mount.
Log of mode switches: `~/.cache/manga-gpu/actions.log`.
