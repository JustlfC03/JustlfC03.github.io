# Homepage badge snapshots

These SVGs preserve the original Shields badge artwork and use Helvetica Neue for
labels and counts (with Helvetica, Arial and sans-serif fallbacks). Flat badges
use regular labels and semibold counts; Code Stars badges retain bold text. They are the local/offline fallback for the homepage and load even
when JavaScript or Shields is unavailable.

Each homepage image keeps its Shields URL in `data-badge-source`. On the published
site, `assets/js/homepage.js` refreshes the source SVG, applies the same typography,
and displays it as an image. The combined GitHub Stars badge continues to use the
validated aggregate from the existing scheduled statistics workflow. Local
previews retain these snapshots.

The snapshots were retrieved on 2026-11-16. The combined Stars value uses the
checked-in `_data/github_stars.json` snapshot; other counts come from their
existing public Shields endpoints.
