# Live Minds Evidence

Status: **VERIFIED**

The synthetic CohortLoom continuity case was verified through official Minds history on
August 22, 2026. This public record intentionally contains only hashes and boolean conclusions.
The redacted evidence artifact remains untracked, and no Mind UUID, raw alias, conversation ID,
message ID, reply body, credential, or personal information is published here.

## Public integrity hashes

- Redacted evidence artifact SHA-256:
  `8cba87c215a148d6f575c31eb461de04f953a665aa332d57d2c47655410059fd`
- Mind fingerprint SHA-256:
  `cf546e745c659f426cf96e305eb612940e25f507e7e6925606dce2981c7686be`
- Unpredictable continuity marker SHA-256:
  `a01ba360c7e5c3c8c447e6b1fa80abd467aa27fb64659b5d387be69c86cfb060`

| Operation | Request SHA-256 | Response SHA-256 |
| --- | --- | --- |
| `store_hypothesis` | `851ccaaea33159792f2edd41837a8ccca52a6c715ed32edbbc2f0b71b5f4afb8` | `5439ae85b62cc2f51cd90384c46c83b1c36c319f1ce98ffafa98f2812101ae45` |
| `recall_and_plan` | `c6ae3ff77b590e6254f22f02802bcd75e214200ec057e8900002c6f21bbe26fa` | `66f7f21a51e8835da1956a373c05ebd277cbba25213993f41d67618fdcd29895` |
| `recall_and_review` | `93ebb65406cc328901dd97e373b13193d18052375e2494a95802eaead74c8dc7` | `ce877bd31990225f86b16e613be62f7e453e67591d186a277d6fde39db358c86` |

## Verified conclusions

| Assertion | Result |
| --- | --- |
| Synthetic content | `true` |
| One store + one plan recall + one due-review recall | `true` |
| Same Mind | `true` |
| Three distinct conversations | `true` |
| Strict response schema valid for all three exchanges | `true` |
| Request-before-reply timestamp order valid for all three exchanges | `true` |
| Outbound request matched official history for all three exchanges | `true` |
| Both fresh recalls matched the approved continuity marker | `true` |
| Due-review request omitted the hypothesis body | `true` |
| Automatic posting or outreach | `false` |
| Automatic recharge | `false` |
| Raw identifiers persisted in the evidence artifact | `false` |

## Evidence boundary

This verifies live Minds persistence and recall for one synthetic, creator-approved experiment
case. It does **not** prove real users, real creator retention, real audience growth, revenue,
public video upload, repository publication, or hackathon submission. Those remain separate
claims and are not inferred from this proof.

The private artifact is excluded from Git by design. The public hashes above allow a later
integrity comparison without exposing the underlying identifiers or reply content.
