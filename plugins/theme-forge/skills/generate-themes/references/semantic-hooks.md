# Semantic hooks — the only shared vocabulary bespoke surfaces carry

Since the bespoke-composition rewrite (2026-09-03), themes no longer share HTML
templates, CSS component classes, or an icon sprite — every surface's markup,
styling, and decoration is authored fresh per theme. That leaves automated
tooling (Gate B rules, `tf_content.py`'s completeness check, design-critic's
seam-hunt) with no fixed class name or tag shape to search for across six
genuinely different structures.

`data-tf-*` attributes are the one exception, and they are **not** a partial
structural-machinery reintroduction: they carry zero CSS, no implied tag
choice, and no layout or visual constraint. A `data-tf-role="primary-cta"`
element can be a `<button>`, an `<a>`, styled as a pill or a hard-edged
rectangle or plain underlined text — the attribute says nothing about any of
that. It exists purely so a machine can find "the element playing this role"
without a human (or an LLM) having to read every theme's bespoke markup by
hand. This is the same spirit as an ARIA role: informational metadata that
never dictates appearance.

**If a surface doesn't emit these attributes, gates degrade — they don't
crash.** A missing `data-tf-role="site-footer"` means the content-completeness
check (`tf_content.py`) can't confirm a footer exists, not that Theme Forge
assumes one exists anyway. Emit the hooks; they cost nothing visually.

## The contract

| Attribute | Values | Used by |
|---|---|---|
| `data-tf-role` | `primary-cta` | Gate B rule 33 (`duplicate-cta-intent`), `tf_content.py` (website: primary-cta presence), design-critic §7b (seam-hunt) |
| `data-tf-role` | `secondary-cta` | Gate B rule 33, design-critic §7b |
| `data-tf-role` | `nav-item` | design-critic §7b (press-feedback seam-hunt) |
| `data-tf-role` | `site-footer` | design-critic's double-footer check, `tf_content.py` (website: footer presence) |
| `data-tf-role` | `data-display` | `tf_content.py` (webapp: at least one data-display element — a table, chart, or stat card) |
| `data-tf-role` | `empty-state` | `tf_content.py` (webapp: empty-state presence) |
| `data-tf-role` | `loading-state` | `tf_content.py` (webapp: loading-state presence) |
| `data-tf-role` | `error-state` | `tf_content.py` (webapp: error-state presence) |
| `data-tf-interaction` | `hold-confirm` | Gate B rule 30 (`asymmetric-timing-absent`, hold-confirm half) |
| `data-screen` | any distinct string per mobile screen | `tf_content.py` (mobile: distinct-screen count), `tf_structure.py` (Gate 18: `screen_count`/`screen_name_multiset`) |

## Rules for using them

- **One role per element.** Don't stack `data-tf-role="primary-cta secondary-cta"` — pick the one that's true.
- **`primary-cta` is singular per surface.** If a surface genuinely has no single dominant action, don't force one; omit the attribute rather than mark two elements primary (that defeats rule 33's duplicate-intent check, which exists precisely to catch two CTAs competing for the same job).
- **Attribute presence is a claim.** Marking a decorative `<div>` as `data-tf-role="data-display"` to satisfy a gate, when nothing about it actually displays data, is worse than omitting the attribute — it teaches the gate a lie. If a surface genuinely has no error/empty/loading state, that's a real content gap `tf_content.py` should catch, not paper over.
- **`data-screen` values must be distinct and non-placeholder.** `data-screen="1"`, `data-screen="2"` pass the count check but fail the intent — use short descriptive names (`data-screen="onboarding"`, `data-screen="checkout"`) since `tf_structure.py`'s mobile signature also reads these values, not just the count.
