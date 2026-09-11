"""Optional Claude helper. Everything works without it.

Used for two things only, and only when Settings → "AI help" is on:
  * a third, fresh explanation when the two curated ones did not land
  * a short reaction to your own-words explanation (explain activities)

Needs the official SDK (`pip install anthropic`) and credentials — an
`ANTHROPIC_API_KEY` env var, or `ant auth login`. Without either, `status()`
says so and the app silently uses the curated text. Nothing about your
progress is sent: only the activity text and what you typed for it.
"""
from __future__ import annotations

SYSTEM = (
    "You are helping an adult beginner learn Python. Plain language, short "
    "sentences, one idea at a time. Never say the learner is lazy or slow. "
    "Do not give the full solution unless the learner already saw it. "
    "Answer in at most 120 words."
)


def status() -> dict:
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return {"available": False, "reason": "The anthropic package is not installed (pip install anthropic)."}
    return {"available": True, "reason": ""}


def _client():
    import anthropic
    return anthropic.Anthropic()


def _ask(model: str, prompt: str) -> dict:
    import anthropic
    try:
        client = _client()
        resp = client.beta.messages.create(
            model=model,
            max_tokens=1024,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "low"},
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        if resp.stop_reason == "refusal":
            return {"ok": False, "error": "The model declined this request."}
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        return {"ok": True, "text": text}
    except anthropic.AuthenticationError:
        return {"ok": False, "error": "No valid credentials. Set ANTHROPIC_API_KEY or run `ant auth login`."}
    except anthropic.RateLimitError:
        return {"ok": False, "error": "Rate limited. Using the curated explanation instead."}
    except anthropic.APIStatusError as e:
        return {"ok": False, "error": f"API error {e.status_code}. Using the curated explanation instead."}
    except anthropic.APIConnectionError:
        return {"ok": False, "error": "No network. Using the curated explanation instead."}


def explain_differently(model: str, activity: dict, tried: list[str]) -> dict:
    prompt = (
        f"Activity: {activity['title']}\nPrompt: {activity['prompt']}\n"
        f"Code (if any):\n{activity.get('code', '')}\n\n"
        "The learner has already read these explanations and asked for a different one:\n"
        + "\n---\n".join(tried)
        + "\n\nGive a genuinely different angle (a new analogy or a step-by-step trace)."
    )
    return _ask(model, prompt)


def react_to_explanation(model: str, activity: dict, learner_text: str) -> dict:
    prompt = (
        f"Question the learner answered: {activity['prompt']}\n"
        f"Model answer: {activity.get('model_answer', '')}\n"
        f"Learner's own words: {learner_text}\n\n"
        "In 2–3 sentences: what did they get right, and what one idea (if any) is missing? "
        "Be specific and kind."
    )
    return _ask(model, prompt)
