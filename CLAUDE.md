# Riverline

We are given this problem to work on from riverline, detailed instructions can be found at [README.md](./README.md) and at the [specification document](./spec.tex) for the whatsapp debt collection agent. The [domain brief](./docs/domain.md) for the debt collection is also important to understand. And there is also the [starter python script](./eval_takehome.py). All data is avl under [data](./data/) dir
There is also the anthropic api key which we can use for claude sonnet, opus inference for intelligent query and analysis of the data. I have stored the api key in [.env](./.env) file at the project root
```bash
ANTHROPIC_API_KEY=...
```

## Planning and Scoping this project

I want you to first construct a plan for buildling a solution to this problem, I also need to build an self contained editor that can visually display the FSM to us, so in the editor in the sidebar we will have the conversation id from 1 - max for selecting the conversation that we are viewing and then in the editor we will have a split plan, on the right we will have the FSM constructed by us and on the left we will have the production conversation, outcomes and annotations data. We don't have to build the entire solution yet, we are just playing aroudn with it and tinkering with as we know and understand more about the data and specs we will get to know and incrementally and iteratively build the solution