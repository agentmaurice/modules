# Image studio

Reusable Module that turns a text brief into reviewed images in Storage,
using only existing tools: the multimodal image and vision tools, Storage
`read_file`/`write_file`, an `llm_call` for planning, and one Go action
compiled to WASM for every deterministic step. An **output profile** (data)
decides how images are planned, prompted, exported, judged and documented;
the Workflows contain no target-specific code.

Two profiles ship with the Module:

| Profile | Export | Use |
|---|---|---|
| [ribin-avatar-item](profiles/ribin-avatar-item.json) | `pixel-grid`: 32x32 text grid, at most 10 colours, `#1b1430` outline, `item.json` in the Ribin cosmetic 1.0.0 format | avatar items (hat, top, accessory) |
| [raster-shop-banner](profiles/raster-shop-banner.json) | `raster`: 1600x400 PNG, centre crop | shop banners |

## Workflows

| Workflow | Role |
|---|---|
| `image-studio-pack` | brief → plan → style sheet → one production per asset (`for_each`, at most 20) → publication |
| `image-studio-render` | one image from a brief with any profile, then publication |
| `image-studio-plan` | the planner model proposes an art direction and a typed asset list; the action normalizes it against the profile (categories, placements, ids, attributes, limits) and reports every repair; stores `plan.json` |
| `image-studio-style-sheet` | one prompt prefix and suffix shared by the whole pack, one self-contained job per asset; stores `style.json` |
| `image-studio-produce-asset` | generation, storage of the source (image buffers last an hour), export, vision review, verdict, then a `decision`: keep, or one corrected second attempt |
| `image-studio-asset-retry` | second and last attempt; a weak result is kept with the `needs_review` status |
| `image-studio-asset-finalize` | writes the kept attempt: exported file, profile document, SHA-256 of every file |
| `image-studio-asset-hold` | effect-free fallback of the decision (the verdict only answers accept or retry) |
| `image-studio-publish` | `manifest.json` (SHA-256 of every file), `review-sheet.png` and `review.json` |
| `image-studio-export` | exports an image already in Storage with a profile, without generation |
| `image-studio-profile-save` | validates a profile and stores it |
| `image-studio-review-read` | returns `review.json` for the `image-studio-review` MiniApp |

A pack lands in `/image-studio/packs/<pack_id>/`: `plan.json`, `style.json`,
one folder per asset (`attempt-1/`, optional `attempt-2/`, the kept export
and its document), `manifest.json`, `review-sheet.png` and `review.json`.
The review sheet shows the assets in manifest order, five per row, with a
status band (green accepted, amber needs review).

Nothing leaves Storage. Publishing or selling an asset is a human decision
taken with the target's own tools after review.

## Review

An attempt is accepted when the vision review passes the profile's minimum
score and the export checks pass (for `pixel-grid`: minimum opaque cells and
box fill ratio). The first refusal triggers one second attempt whose prompt
carries the reasons; the second attempt is always kept, flagged
`needs_review` when it still fails. An unreadable review is never an
acceptance. Workflow V2 has no retry loop, so the two attempts are unrolled.

The `pixel-grid` export removes the background by flood fill from the image
border, then **defringes**: it grows the background through pixels that are
mostly background along a segment towards a solid subject colour (anti-aliased
seams and soft glows, such as a halo around a bell) and recolours the
remaining seam with that subject colour. The profile prompt also asks for a
flat background without glow.

## Output profiles

A profile is an `image-studio.profile/v1` JSON document:

- `planning`: guidance for the planner, `max_assets`, `id_pattern`,
  `categories` (key, `id_prefix`, description, optional `placements`,
  `framing` added to the prompt so the object fits its export box, and
  `review` telling the vision reviewer how the export shows the category) and
  enumerated `attributes`;
- `generation`: `aspect_ratio`, optional logical `model`, `style_prefix`,
  `composition`, `background`, `avoid`;
- `export`: `pixel-grid` (`size`, `max_colors`, `outline`, `letters`,
  `preview_scale`, `background.tolerance`, `background.defringe`,
  `background.clear_enclosed` (also clears background-coloured holes), one `boxes`
  entry per category and `category:placement`, each with an optional
  `keep_top` fraction of the subject's height kept from its top) or `raster` (`width`,
  `height`, `fit` `cover` or `contain`, `file`);
- `judge`: vision `prompt`, `min_score`, `min_opaque_cells`,
  `min_box_fill_ratio`;
- `document` (optional): `file`, `template`, `fields` mapped from
  `asset.id`, `asset.title`, `asset.category`, `asset.placement`,
  `asset.attributes.<name>`, `pack.id`, `pack.theme`, `export.art`, and
  `by_attribute` objects merged per attribute value;
- `pricing` (optional): a suggested price per attribute value, recorded in
  the manifest; nothing is put on sale.

Store a profile with `image-studio-profile-save` (`profile`, `path`).

## Prerequisites

- WASM code execution enabled, with the light `sandbox-worker`.
- The image capability (`multimodalconfig/image`) and the vision capability
  (`multimodalconfig/vision`) configured on the Agent, multimodal tools
  allowed (`maurice test setup --multimodal` for a test Agent), then the Agent
  redeployed so the multimodal tools are published.
- A run LLM profile on the Agent for the planner `llm_call`.

## Go/WASM action

The source is [wasm/studio](wasm/studio): `go.mod` and the Module's own code.
The workflow SDK is supplied by `maurice module wasm build` and `test`; it is
never committed here. Each code step pins the artifact recorded in
[tooling/image-studio/artifact.json](../tooling/image-studio/artifact.json).
After a source change:

```sh
maurice module wasm test --dir image-studio/wasm/studio
maurice module wasm build --dir image-studio/wasm/studio --out <bundle> \
  --key-id <builder> --signing-key <key> \
  --capability call_tool --capability buffer_load --capability wasi.clock --capability wasi.random
# record artifact.sha256 and artifact.size of <bundle>/manifest.json in artifact.json
python3 tooling/image-studio/build.py
```

Two builds of the same source with the same CLI give the same artifact. The
operator then publishes and binds the bundle to the target Agent
(`maurice module wasm publish`, `bind`) before deploying the Workflows.

## Installation

Validate with `maurice module validate --file image-studio/module.yaml`.
Install either with the Application rail (`maurice app add --dev`, `app plan`,
`app apply`) or by composing `agents/main/workflows` and
`agents/main/miniapps` into the consumer Agent Spec project and running
`maurice spec check` and `spec deploy`. Then store the profiles with
`image-studio-profile-save`.

## Example

[examples/christmas-2026-brief.md](examples/christmas-2026-brief.md) is the
brief of the Christmas 2026 "Deer and elves" demonstrator pack:

```json
{"brief": "<brief text>", "pack_id": "noel-2026", "theme": "noel-2026",
 "profile_path": "/image-studio/profiles/ribin-avatar-item.json", "max_assets": 12}
```
