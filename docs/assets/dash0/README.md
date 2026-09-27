# Dash0 visuals

These walkthroughs show the real H100 workload after replay into Dash0. The source screenshots are actual Dash0 UI captures. Their provenance and hashes are recorded in [screenshot-provenance.json](../../evidence/screenshot-provenance.json). Cropping, magnification and colored outlines guide attention; displayed telemetry values are unchanged.

## Visual identity and credit

Dash0 is the hosted observability platform used in this project. This independent community project is not an official Dash0 product.

- The unmodified [white Dash0 logo](https://www.dash0.com/shared/logo-white.svg) was retrieved from the [official Dash0 website](https://www.dash0.com/) on September 27, 2026. `logo-white.png` is a transparent 2× rasterization of that SVG for the GIF renderer. The logo belongs to Dash0 and is not covered by this repository's MIT license.
- The authored frames and diagrams use the site's observed coral `#f8494d`, orange `#fd8c66`, background `#101010` and charcoal surfaces. This is an adaptation of the website palette, not a claim of compliance with a published brand guide.
- Typography uses portable system/Pillow fonts. No proprietary Dash0 fonts are bundled.
- Warm highlights belong to the walkthrough framing; the source UI screenshots retain their original appearance.

## Rebuild

Run from the repository root:

```bash
.venv/bin/python scripts/replay/build_diagrams.py
.venv/bin/python scripts/replay/build_walkthroughs.py
```

The SVG builder embeds the original logo paths so GitHub does not need to resolve external images inside diagrams. The GIF builder uses the committed logo PNG and the committed UI screenshots. It preserves the quick zooms and two-second focused holds. Focused preview frames are written under ignored `artifacts/animation-preview/` for visual review.

To regenerate the logo PNG after intentionally updating its source, install CairoSVG in an isolated environment and render the SVG at 210 × 40 pixels. CairoSVG is not a runtime dependency of the replay or GIF builder.
