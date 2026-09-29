# Grizzly Greens editorial and visual standard

This standard applies to every article rebuilt after GG-A2. Existing article URLs and valid search intent stay intact. Rebuilds are reviewed one article at a time; automation handles metadata and mechanical checks, not diagnosis or horticultural advice.

## Editorial acceptance

1. State the homeowner's answer in the first paragraph. Name what can be checked today and when the answer depends on grass species, climate, soil, or season.
2. Organize around decisions: observable signs, simple tests, likely explanations, action sequence, stop conditions, and when local Extension or a qualified professional is needed. Remove repeated summary sentences and near-identical section frames.
3. Distinguish symptoms from causes. Do not identify fungus, insects, compaction, nutrient deficiency, or dead turf from appearance alone. Avoid universal watering, fertilizer, chemical, or mowing schedules.
4. Support material factual claims with current primary horticultural or agricultural sources, preferably land-grant university Extension. Link sources in a short Sources section. Recheck dates and regional applicability at review time.
5. Explain what a reader should do with each fact. Keep useful related-page links to distinct next questions, and confirm targets exist. Avoid links added solely for volume.
6. Preserve the published date when supported by the existing page or Git history. Set `dateModified` to the actual substantive rewrite date. Use a single valid `Article` JSON-LD object with matching canonical URL, headline, description, image, and dates. Never claim an individual expert author who did not review the page.
7. An editor must check clarity, evidence, factual limits, accessibility, links, and final rendering before publication. Word count is a diagnostic, not an acceptance threshold.

## Visual acceptance

1. Use a visual only when it teaches an observation, comparison, test, process, or decision. Show a photo as an example, not proof of diagnosis. Label conceptual/generated imagery as an illustration in its caption.
2. Standard article image: 1600 × 900 WebP, target under 600 KB, natural color, no burned-in text. Use `width`, `height`, descriptive alt text, `loading="lazy"`, and `decoding="async"`. The figure must remain understandable without the image through the surrounding text.
3. The article's `og:image`, `twitter:image`, and JSON-LD `image` point to the same absolute 1600 × 900 URL. Do not use an unrelated sitewide default for a rebuilt article.
4. Keep provenance in the project record or adjacent asset manifest, including image-generation prompt or source/rights and an editorial verification note. Original AI illustrations must not masquerade as field photographs or definitive species/disease identification.
5. Prefer deterministic SVG/HTML for precise diagrams, scales, and labels. Require individual review of factual photographs, pest/disease identification, product depictions, and safety steps.

## Batch gate

For each batch, compare the original and replacement, verify source support and dates, validate JSON-LD, canonical, links, image decode/dimensions/size, sitemap/search-index consistency, mobile layout, and live responses after GitHub Pages deployment. Retain only the current accepted assets and concise batch record; Git is source history.
