# The six slots

Six slots keep the set spread out. Each maps to one direction from
`knowledge/04-aesthetics.md`. The slot is the *role in the set*; the direction is the concrete
aesthetic you assign to fill it.

| Slot | Role | Typical direction(s) |
|---|---|---|
| A | The safe one — restrained, professional, obviously shippable | Quiet Professional, Swiss Minimal |
| B | The confident one — saturated, expressive, strong personality | Confident Saturate, Expressive Material |
| C | The typographic one — editorial, type-led, minimal ornament | Editorial Type-Led |
| D | The technical one — dark-first, dense, tool-like | Technical Dark |
| E | The human one — warm, organic, softer geometry | Warm Human, Organic Soft |
| F | The swing — whatever the brief secretly wants | Neo-Brutalist, Retro-Futurist, Bento Modular, Liquid Glass |

## Rules for a good set

- **Differ on at least two of:** color strategy, type character, geometry. Two low-chroma
  sans-serif small-radius themes are the same theme with different hues, and the user will say
  so.
- **Primary hues at least ~30° apart.** The `design-critic` flags any pair within 20°.
- **Distinct type stacks.** Don't give three themes Inter/Inter. Vary display and body faces,
  and draw body faces from the default set in `knowledge/03-typography.md` (Geist, Bricolage,
  Fraunces, Instrument, Newsreader, Source Serif 4, Satoshi, General Sans) rather than
  defaulting to Inter / Roboto / Space Grotesk unless the brief asks.
- **Distinct radii.** A near-zero editorial, a small professional, a large human.

## Adapt to the brief

- A children's education product: drop Technical Dark; lean Warm Human, Expressive Material,
  Bento, playful Confident Saturate.
- A compliance dashboard: Quiet Professional, Swiss, Technical Dark, one confident option to
  clarify what they actually want.
- Even a conservative brief benefits from one genuinely unexpected option (slot F) — it
  clarifies preferences cheaply.

## When native is the primary platform

Bias toward directions that survive translation (see `11-native-platform.md`):

- **Safe on device:** Quiet Professional, Technical Dark, Swiss Minimal, Warm Human, Bento.
- **Needs care:** Confident Saturate (colored shadow → border on Android), Neo-Brutalist (hard
  shadow impossible on Android → border), Retro-Futurist (gradients need `expo-linear-gradient`;
  glow unavailable on Android).
- **At most one per set:** Liquid Glass and any other `expo-blur`-dependent direction. Four of
  six depending on `backdrop-filter` or fluid type will collapse into sameness on device.

## Let the user swap one

Print the six one-line directions and offer a swap before generating. Cheap, and it
dramatically improves the hit rate.
