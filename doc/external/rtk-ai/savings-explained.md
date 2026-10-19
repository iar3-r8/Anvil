# RTK — savings explained

Source: https://www.rtk-ai.app/docs/resources/savings-explained/
Retrieved: 2026-10-19 (fetched by the tdd-manager via oxylabs `universal_scraper` during the RTK spike, [plans/rtk-spike.md](../../plans/rtk-spike.md); transcribed here, not re-fetched)

What RTK's reported savings measure, how the reduction dilutes from bytes to cost, and what RTK does not reduce.

RTK cuts up to 90% of the bash output your agent reads. The only thing RTK
changes is **the bytes a shell command sends back**. Everything RTK reports as
"savings" is measured on those bytes.

The savings chain:

    Cost
    ├─ Input tokens
    │  ├─ Bash output           <- the only part RTK filters
    │  ├─ Your prompt
    │  ├─ System prompt
    │  └─ Conversation history
    └─ Output tokens            <- what the model writes

Those bytes are one contributor to input tokens, alongside your prompt, the
system prompt, and conversation history. Input tokens are in turn only part of
the bill, which also counts output tokens. So the reduction dilutes at every
step: a large cut in bash output produces a smaller cut in input tokens, and a
smaller one again in cost. A command showing 90% fewer output bytes does not
make your session 90% cheaper.

Why the token counts are estimates: `rtk gain` estimates tokens as
`bytes / 4` (rounded up). RTK ships **no tokenizer**, so the percentage is
reliable (same estimator on raw and filtered), but the absolute token counts
are approximate and will not match your provider's billing.

What RTK does not reduce: output tokens; your prompt, the system prompt, or
conversation history; commands with no matching filter (pass through
untouched, tracked at 0% savings).
