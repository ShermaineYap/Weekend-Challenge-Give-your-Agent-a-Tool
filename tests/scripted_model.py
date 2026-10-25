"""A deterministic Strands Model that replays scripted turns — lets us test the
full agent loop (tools, hooks, invocation_state) offline, with no Bedrock calls."""

import json
from typing import Any

from strands.models.model import Model


class ScriptedModel(Model):
    def __init__(self, turns: list[list[dict]]):
        # each turn: list of blocks, {"text": "..."} or {"tool": name, "input": {...}}
        self.turns = list(turns)
        self.calls = 0

    def update_config(self, **kw):  # noqa: D401
        pass

    def get_config(self):
        return {}

    async def structured_output(self, *a, **k):
        raise NotImplementedError

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs: Any):
        turn = self.turns.pop(0) if self.turns else [{"text": "Done."}]
        self.calls += 1
        yield {"messageStart": {"role": "assistant"}}
        stop = "end_turn"
        for i, b in enumerate(turn):
            if "tool" in b:
                stop = "tool_use"
                yield {"contentBlockStart": {"start": {"toolUse": {"toolUseId": f"t{self.calls}-{i}", "name": b["tool"]}}}}
                yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(b["input"])}}}}
                yield {"contentBlockStop": {}}
            else:
                yield {"contentBlockStart": {"start": {}}}
                yield {"contentBlockDelta": {"delta": {"text": b["text"]}}}
                yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": stop}}
