# Riverline

We are given this problem to work on from riverline, detailed instructions can be found at [INFO.md](./INFO.md) and at the [specification document](./spec.tex) for the whatsapp debt collection agent. The [domain brief](./docs/domain.md) for the debt collection is also important to understand. And there is also the [starter python script](./eval_takehome.py). All data is avl under [data](./data/) dir
There is also the anthropic api key which we can use for claude sonnet, opus inference for intelligent query and analysis of the data. I have stored the api key in [.env](./.env) file at the project root
```bash
ANTHROPIC_API_KEY=...
```

## Docs

All docs of the progress and things done so far are stored in ./docs/agents/handoff/*

## Progress

Read the @eval_takehome.py script for the current state of the evaluator
more docs are avl under @/docs/agents/handoff

## Notes

Remember because this is an assignment, they have intentionally also sliently added a lot fo bugs, failures and random disturbances in the production data and maybe the outcomes and annotations, we will have to be careful in our analysis and experiment to not take any assumptions at all and rigorously find and stress test on our hypothesis and evaluator
They will also later test our evaluator on hidden test set which will have more disturbances and different distribution, so it is very important they we closely follow the @spec.tex document all the time

Some of the data quality issues, bugs, disturbances which I was able to find are:
1. Inconsistent numbering: The turn numbering of the conversation is also inconsistent, turn 0-4 are one per message while turn 5 onward bot and borrower share the same turn number
2. Off turn texts: there are a lot of cases where the message used by the bot classifier for intent flagging is completely different from the actual borrower message, 14 texts were from a different turn and 33 never occurred in the entire corpus. One of those 33 was classified as refuses when the actual message was "Please anything lower Priya ji... I'm telling you honestly I barely have enough to feed my family right now." which is clearly hardship
3. 