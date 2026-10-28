"""Claude on Amazon Bedrock as the DeepEval judge (Anthropic SDK Bedrock client), with token accounting."""
import asyncio
import contextvars
import json
import threading
import time

import anthropic
from deepeval.models import DeepEvalBaseLLM

import config

# Which test row / metric a judge call belongs to; set by run_eval before each measure (copied into worker threads).
CURRENT = contextvars.ContextVar("judge_call_tag", default=("-", "-"))

# USD per million tokens (input, output) - Anthropic list prices as a reference; Bedrock bills its own rate card,
# so set JUDGE_PRICE_IN / JUDGE_PRICE_OUT in .env to your actual rates.
LIST_PRICES = {"claude-opus-5-5": (4.00, 20.00), "claude-sonnet-5-5": (2.00, 10.00), "claude-haiku-5-5": (0.10, 0.50),
               "claude-opus-5": (5.00, 25.00), "claude-sonnet-5": (2.00, 10.00), "claude-haiku-4-5": (1.00, 5.00),
               "claude-opus-4-8": (5.00, 25.00)}
NO_EFFORT = ("haiku-4-5", "sonnet-4-5")  # these models reject output_config.effort


def price_for(model_id):
    if config.JUDGE_PRICE_IN is not None and config.JUDGE_PRICE_OUT is not None:
        return config.JUDGE_PRICE_IN, config.JUDGE_PRICE_OUT
    return next((p for name, p in LIST_PRICES.items() if name in model_id), (None, None))


class BedrockClaudeJudge(DeepEvalBaseLLM):
    def __init__(self, model_id=config.JUDGE_MODEL):
        self.model_id = model_id
        self.usage = []  # one dict per API call
        self.live_file = None  # optional path: each call's usage is also appended here as it happens (progress.py)
        self._lock = threading.Lock()
        self._no_native_json = False
        super().__init__(model_id)

    def load_model(self):
        # Bedrock has no server-side refusal fallback; the SDK middleware re-runs a policy decline on the fallback model.
        # betas=[]: Bedrock in.* profiles reject the middleware's default fallback-credit beta header.
        middleware = ([anthropic.BetaRefusalFallbackMiddleware([{"model": config.JUDGE_FALLBACK_MODEL}], betas=[])]
                      if config.JUDGE_FALLBACK_MODEL else None)
        # Credentials come from the standard AWS chain (env vars / eval/.env, ~/.aws profile, role).
        # The Bedrock runtime client: in ap-south-1 Claude is served through inference profiles (in.* / global.*),
        # which the newer Mantle endpoint does not serve there (404 on 16-Oct-2026).
        return anthropic.AnthropicBedrock(aws_region=config.AWS_REGION, middleware=middleware, max_retries=4)

    def _record(self, message, seconds):
        u = message.usage
        hops = getattr(u, "iterations", None) or [u]  # with a fallback, every attempt is billed separately
        rec = {"row": CURRENT.get()[0], "metric": CURRENT.get()[1], "model": getattr(message, "model", self.model_id),
               "input_tokens": sum(getattr(h, "input_tokens", 0) or 0 for h in hops),
               "output_tokens": sum(getattr(h, "output_tokens", 0) or 0 for h in hops),
               "cache_read_tokens": sum(getattr(h, "cache_read_input_tokens", 0) or 0 for h in hops),
               "cache_write_tokens": sum(getattr(h, "cache_creation_input_tokens", 0) or 0 for h in hops),
               "attempts": len(hops), "seconds": round(seconds, 2)}
        with self._lock:
            self.usage.append(rec)
            if self.live_file:
                with open(self.live_file, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec) + "\n")

    def _create(self, prompt, output_config):
        t0 = time.monotonic()
        kwargs = {"output_config": output_config} if output_config else {}
        message = self.model.beta.messages.create(
            model=self.model_id, max_tokens=16000, messages=[{"role": "user", "content": prompt}], **kwargs)
        self._record(message, time.monotonic() - t0)
        if message.stop_reason == "refusal":
            raise RuntimeError(f"Judge declined to grade: {message.stop_details}")
        return next(b.text for b in message.content if b.type == "text")

    def generate(self, prompt, schema=None):
        # effort = depth of thinking, the main cost lever after the model choice
        base = {} if any(x in self.model_id for x in NO_EFFORT) else {"effort": config.JUDGE_EFFORT}
        if schema is None:
            return self._create(prompt, base)
        json_schema = anthropic.transform_schema(schema)
        if not self._no_native_json:
            try:
                return schema.model_validate_json(self._create(prompt, {**base, "format": {"type": "json_schema", "schema": json_schema}}))
            except anthropic.BadRequestError as e:
                if "format" not in str(e):
                    raise
                self._no_native_json = True  # e.g. in.* India profiles on Bedrock reject output_config.format
        text = self._create(prompt + "\n\nReply with ONLY a JSON object (no prose, no code fence) that matches this JSON "
                            "schema:\n" + json.dumps(json_schema), base)
        return schema.model_validate_json(text[text.find("{"):text.rfind("}") + 1])

    async def a_generate(self, prompt, schema=None):
        return await asyncio.to_thread(self.generate, prompt, schema)

    def get_model_name(self):
        return f"{self.model_id} (Bedrock {config.AWS_REGION})"
