# Riverline

We are given this problem to work on from riverline, detailed instructions can be found at [README.md](./README.md) and at the [specification document](./spec.tex) for the whatsapp debt collection agent. The [domain brief](./docs/domain.md) for the debt collection is also important to understand. And there is also the [starter python script](./eval_takehome.py). All data is avl under [data](./data/) dir
There is also the anthropic api key which we can use for claude sonnet, opus inference for intelligent query and analysis of the data. I have stored the api key in [.env](./.env) file at the project root
```bash
ANTHROPIC_API_KEY=...
```

## Docs

All docs of the progress and things done so far are stored in ./docs/agents/handoff/*

## Progress

1. We have trained a borrower intent classifier that works reasonably well and with good accuracy @docs/approach.md