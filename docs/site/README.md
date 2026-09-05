# Portfolio pages — production source

The `.qmd` files here are the **production copies** of the project pages on
[velezf.github.io](https://velezf.github.io/projects.html). Edit here, then copy into the site
repo; never edit only the site copy (the two drifted silently once — see the deploy memory).

| Page | Site path | Listing card |
|---|---|---|
| `lora-radiorocket-v2.qmd` | `projects/lora-radiorocket-v2.qmd` | `images/card-lora-radiorocket-v2.jpg` → site `images/lora-radiorocket-v2.jpg` |
| `apogee-handheld.qmd` | `projects/apogee-handheld.qmd` | `images/card-apogee-handheld.jpg` → site `images/apogee-handheld.jpg` |

The V1 page (`projects/lora-radiorocket.qmd`) and the flight archive
(`projects/lora-flights.qmd`) are unchanged by these pages and stay where they are.

## Images

Pages reference images by **raw GitHub URL** into `docs/site/images/` on `main`, the same
convention the V1 page uses for its build photos. That means the images resolve only after
this folder is merged and pushed; until then a local render shows broken images but no errors.

- `v2-*.jpg` — photos, downscaled to 1600 px from the 2026-09-05 set.
- `gs-oled-*.png` — ground-station OLED pages, rendered by `ground/oled` (`frame_spec` +
  `draw.render`) with the 2026-08-25-F1 numbers, upscaled 4×.
- `hh-*.png` — handheld screens, rendered by `handheld/app/render.py` driven through the real
  `GuessGame` state machine, upscaled 4×.
- `card-*.jpg` — 1536×1024 listing cards for the site's project grid.

Regenerate the screens with the script that produced them (kept in the session scratchpad, not
the repo) or by calling the two renderers directly; they are pure functions of their inputs.

## Deploy

```sh
SITE=/Users/renatus/velezf.github.io
cp docs/site/lora-radiorocket-v2.qmd docs/site/apogee-handheld.qmd $SITE/projects/
cp docs/site/images/card-lora-radiorocket-v2.jpg $SITE/images/lora-radiorocket-v2.jpg
cp docs/site/images/card-apogee-handheld.jpg     $SITE/images/apogee-handheld.jpg
cd $SITE && quarto render projects/lora-radiorocket-v2.qmd && quarto render projects/apogee-handheld.qmd
# commit + push the site repo; GitHub Actions renders and deploys
```

Neither page executes code, so no Jupyter kernel or `QUARTO_PYTHON` is needed to render them.
