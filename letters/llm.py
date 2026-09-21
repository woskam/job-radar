"""
Shared Claude API call handling for the four places this project calls the
model (generator.py, interview_prep.py, cv_tailor.py, setup_wizard.py).

Introduced after a code review found that none of the four checked
`response.stop_reason` -- a reply cut off by hitting max_tokens (thinking
tokens count against the ceiling too, and it was often only 2000-3000) or a
reply with no text block at all (thinking used the whole budget) was
returned and saved as if it were a finished, successful draft. See
ModelReplyError's callers for what happens once a reply is rejected here.
"""

import os

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
# A ceiling on spend per reply, not a target length -- you pay for tokens
# actually generated, so a generous ceiling costs nothing when the reply is
# short. Shared across all four call sites rather than each guessing its
# own number.
MAX_TOKENS = 16000


class ModelReplyError(RuntimeError):
    """The model replied, but the reply cannot be used as-is."""


def reply_text(response) -> str:
    if response.stop_reason == "max_tokens":
        raise ModelReplyError("reply was cut off at max_tokens")
    if response.stop_reason == "refusal":
        raise ModelReplyError("the model declined the request")
    text = "\n".join(b.text for b in response.content if b.type == "text").strip()
    if not text:
        raise ModelReplyError(f"reply contained no text (stop_reason={response.stop_reason})")
    return text
