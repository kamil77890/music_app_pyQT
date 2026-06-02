## Cover Color Extraction Design

### Goal

The backend should return representative cover-derived values for `dominantColor` and `colorPalette` for song responses. The existing JSON contract remains unchanged:

```json
{
  "dominantColor": "#RRGGBB",
  "colorPalette": ["#RRGGBB", "#RRGGBB", "#RRGGBB"]
}
```

Fallback `#808080` is allowed only when no cover is provided, the cover cannot be opened or processed, or the image is effectively monochromatic with no saturated accent color.

### Scope

The change is focused on `app/logic/color_extractor.py`, which is already used by playlist/song enrichment and persistence paths. Song-list endpoints that expose covers should use this extractor so `dominantColor` and `colorPalette` are present wherever the frontend expects them. Endpoints should not add new debug response fields. Fallback reasons are logged on the server.

### Algorithm

1. Open the cover image from a local path, URL, or base64-like cover value and convert it to `RGBA` so alpha can be filtered.
2. Resize the image to about `160x160` for deterministic, fast processing.
3. Iterate pixels and ignore:
   - `alpha < 128`
   - brightness below `20`
   - brightness above `235`
   - saturation below `0.18` for the primary dominant-color pass
4. Quantize remaining pixels into coarse RGB buckets, using a fixed channel step.
5. Score each bucket using frequency, saturation, and mid-brightness preference.
6. Select the highest-scoring bucket as the accent color.
7. If no bucket passes the saturated-color filter, scan valid non-transparent, non-extreme pixels for the most saturated accent candidate.
8. If no saturated accent exists, return the gray fallback and log `fallback_reason="no_saturated_pixels"`.

### Palette

`colorPalette` is generated from the selected accent color:

1. Accent / dominant color.
2. Darker variant for secondary UI surfaces.
3. Very dark variant for gradients.

The darker variants preserve hue and saturation while lowering brightness, rather than choosing unrelated pixels.

### Fallback Logging

Server logs include a short structured reason for fallback, for example:

- `fallback_reason="no_cover"`
- `fallback_reason="cover_download_failed"` for failed remote covers
- `fallback_reason="invalid_image"` for unreadable local/base64 images
- `fallback_reason="no_saturated_pixels"`

The JSON response remains compatible and does not include the fallback reason.

### Tests

Backend tests cover:

1. A colorful cover returns a non-gray `dominantColor`.
2. The same image returns the same result across repeated calls.
3. Missing cover returns fallback `#808080`.
4. A monochromatic gray cover may return fallback `#808080`.
5. An image with black letterbox bars and a colorful center ignores the bars and returns the center accent.
