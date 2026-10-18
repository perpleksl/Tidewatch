# Spike R3: model bake-off on meme classification (PER-17)

*Run on 19 Oct 2026 (GitHub Actions run 39170343285). 100 tokens, labels approved by the Owner. Total cost **$0.45**.*

## Short answer

- **The cheap worker model is as good as Claude Haiku**, at a tiny fraction of the cost: `deepseek-v4.1-flash` on Surplus was **92% right** (Haiku also 92%, Sonnet 95%) and gave identical answers on both runs.
- **Escalate every low-confidence answer to the professor.** That sends ~11% of tokens to Sonnet and lifts accuracy to **93%** for **~$7/month** at 500 new tokens a day (Sonnet on everything would be ~$60/month). It also rescues **$MASK**: the worker called Nullmask a meme (low confidence), and Sonnet correctly says it isn't.
- **Almost every remaining "mistake" is a definition question, not a model failure.** For 6 tokens that **started as memes but now have a product or their own chain** (Dogecoin, Bonk, Shiba Inu, Floki, Pepe Unchained, Degen), you labelled *meme*, and all four models mostly said *not meme*, citing the product. **Your decision is needed** (see the end).
- **The reviewer model `deepseek-v4-pro-0813` is unreliable for this task:** 18% of its answers came back empty. It's a reasoning model that used up its whole answer budget thinking.

## Results

Accuracy compares the first run of each setup with your labels. "Clear" covers the 85 non-borderline tokens.

| Setup | Model (provider) | Answered | **Accuracy** | Clear | Borderline | High-confidence answers correct | Cost per token | **Monthly at 500 tokens/day** |
|---|---|---|---|---|---|---|---|---|
| Worker | `deepseek-v4.1-flash` (Surplus) | 99/100 | **92/99 (93%)** | 84/85 | 8/14 | 84/89 | $0.000006 | **$0.09** |
| Reviewer | `deepseek-v4-pro-0813` (Surplus) | 82/100 | 76/82 (93%) | 72/74 | 4/8 | 70/76 | $0.00013 | $1.90 |
| Fallback | `claude-haiku-5-5` (Anthropic) | 100/100 | **92/100** | 84/85 | 8/15 | 72/75 | $0.00026 | $3.93 |
| Professor | `claude-sonnet-5-5` (Anthropic) | 100/100 | **95/100** | 84/85 | 11/15 | **77/77** | $0.0040 | $59.78 |
| **Recommended:** worker, with low-confidence or unreadable answers escalated to Sonnet | | 100/100 | **93/100** | | | | ~$0.00044 | **~$6.70** |

Costs come from the run's `CostEntry` rows: Surplus as it reported each charge, Anthropic from the official price list. The one "clear" token every model missed is **Dogecoin** (see the definition question).

Every answer has a label, a confidence, a 1–3 sentence rationale and at least one source link taken from the token's profile. The exceptions are a handful of unreadable worker/reviewer answers, listed in `R3-results.csv`.

## Borderline cases and the reference cases

| Token | Your label | Worker | Reviewer | Haiku | Sonnet |
|---|---|---|---|---|---|
| Bonk | meme | ❌ not meme | ❌ not meme | ❌ not meme (low) | ❌ not meme (low) |
| Shiba Inu | meme | ❌ not meme | ❌ not meme | ❌ not meme | ✅ meme (low) |
| Floki | meme | ❌ not meme | ❌ not meme | ❌ not meme | ❌ not meme (low) |
| Turbo | meme | ✅ meme | ✅ meme (low) | ✅ meme | ✅ meme |
| Pudgy Penguins | meme | ✅ meme | ✅ meme | ✅ meme (low) | ✅ meme |
| Goatseus Maximus | meme | ✅ meme | — | ✅ meme (low) | ✅ meme (low) |
| Pepe Unchained | meme | ❌ not meme (low) | — | ❌ not meme (low) | ❌ not meme (low) |
| Degen | meme | ❌ not meme | ❌ not meme | ❌ not meme (low) | ✅ meme (low) |
| Notcoin | not meme | — | — | ❌ meme (low) | ✅ not meme (low) |
| Hamster Kombat | not meme | ✅ not meme (low) | — | ❌ meme (low) | ✅ not meme (low) |
| ai16z / elizaOS | not meme | ✅ not meme | — | ✅ not meme (low) | ✅ not meme (low) |
| Zerebro | meme | ✅ meme (low) | — | ✅ meme (low) | ❌ not meme (low) |
| Act I: The AI Prophecy | meme | ✅ meme (low) | ✅ meme (low) | ✅ meme (low) | ✅ meme (low) |
| **Nullmask ($MASK)** | not meme | ❌ **meme (low)** | — | ✅ not meme (low) | ✅ not meme (low) |
| Virtuals Protocol | not meme | ✅ not meme | ✅ not meme | ✅ not meme | ✅ not meme |
| Dogecoin | meme | ❌ not meme | ❌ not meme | ❌ not meme | ❌ not meme (low) |
| **Pearl ($PRL)** | not meme | ✅ not meme | ✅ not meme | ✅ not meme | ✅ not meme |
| Mask Network (same ticker as $MASK) | not meme | ✅ not meme | ✅ not meme | ✅ not meme | ✅ not meme |

"—" means the answer was empty or unreadable.

**Confidence is a useful signal.** Sonnet's *high*-confidence answers were 77/77 correct, and every Sonnet miss was *low* confidence. The worker's wrong answers were mostly *high* confidence, but nearly all of them are the definition cases above.

## Signs of model substitution (risk R9)

- **Consistency:** both Surplus models were run twice. Every token answered in both runs got **the same label both times**: 96/96 for the worker and 75/75 for the reviewer. There's no sign of answers coming from different models between runs.
- **Quality:** the worker matched Claude Haiku exactly (92% each) and agreed with Sonnet on all clear tokens but Dogecoin. That isn't "far below" what this model family should do.
- **Price:** the worker cost **$0.000006 per classification**, roughly $0.01 per million tokens. That's implausibly far below DeepSeek's own list prices, which echoes the AD9 concern. Quality doesn't currently suggest a swapped model, but the price means Surplus supply could change or vanish without notice. The fallback to Haiku (PER-14) already covers that.
- **Conclusion:** no evidence of substitution in this run. Keep the AD9 rule that **no worker or reviewer output is ever shown to you as a final judgment**.

## Recommendations

1. **Worker tier:** keep `deepseek-v4.1-flash` on Surplus for first-pass meme classification. No change to the AD9 default.
2. **Escalation rule:** send a token to the **professor (Sonnet)** when the worker's answer is **low confidence, unreadable, or says "No product materials found"**. That was ~11% of tokens in this sample. In M1 this becomes a code rule, not a setting value, unless you want it adjustable.
3. **Reviewer tier:** don't use `deepseek-v4-pro-0813` for short structured answers like this one. 18% of its answers were empty because its reasoning used up the budget. For the reviewer's real tasks (triage, social authenticity, GitHub first read) the reviewer prompts need a larger output budget, and the PER-17-style check should be re-run on those tasks. *A possible AD9 change, to decide separately:* use `deepseek-v4.1-flash` for the reviewer tier too, if the reviewer tasks don't need a reasoning model.
4. **Haiku as fallback:** fine (92%). It's slightly worse than the worker on game tokens: it called Notcoin and Hamster Kombat memes.
5. **The meme definition: your decision.** See below. Once decided, PRD 3.2 and the prompt get the rule, and this bake-off can be re-run for ~$0.50.

## Decision needed: tokens that started as memes but now have a product

The models apply PRD 3.2 literally: *"MEME if its value proposition is mainly culture, humour… with **no real product, protocol or network** that the token is needed for."* Dogecoin has its own chain, Bonk has a launchpad, DEX and trading bot, Shiba Inu has an L2, Floki has a game, and Pepe Unchained and Degen have chains. So the models call them *not meme*. You labelled them *meme*.

| Option | Rule | Effect |
|---|---|---|
| **A. Meme by origin** | "If the token launched as a meme, it stays a meme, even if products were built around it later." | All 6 become memes and are excluded. Write it into PRD 3.2 and the prompt. Accuracy against your labels would likely rise to ~98% (to be confirmed with a ~$0.50 re-run). |
| **B. Meme by today's substance** | "Judge what the token is needed for today." | Keep the current prompt and flip those 6 labels to *not meme*. They'd appear in the tabs and be judged on risk instead. |

## Files

- `docs/spikes/R3-sample.csv`: the 100 tokens with your labels.
- `docs/spikes/R3-results.csv`: one row per token per setup per run (600 rows), with label, confidence, rationale, sources, model, provider and cost.
- `backend/scripts/meme_bakeoff.py` and Actions → "Meme bake-off": re-run any time, for ~$0.45.
