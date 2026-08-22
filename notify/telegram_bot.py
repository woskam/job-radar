import os
from pathlib import Path

import requests
from dotenv import load_dotenv

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/{method}"


def _api_url(method: str) -> str:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    return TELEGRAM_API_URL.format(token=token, method=method)


def build_approval_request_text(job: dict) -> str:
    score = job.get("relevance_score")
    score_text = f"{score:.2f}" if score is not None else "?"
    text = (
        f"New match -- write a letter?\n\n"
        f"{job.get('title')} at {job.get('company')}\n"
        f"Location: {job.get('location')}\n"
        f"Score: {score_text}"
    )
    if job.get("url"):
        text += f"\n\n{job['url']}"
    return text


def _chunk_text(text: str, max_len: int = 3500) -> list[str]:
    # Telegram's sendMessage limit is 4096 characters -- split on paragraph
    # boundaries, and hard-cut if a single paragraph is already too long.
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) > max_len and current:
            chunks.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        chunks.append(current)

    final: list[str] = []
    for chunk in chunks:
        while len(chunk) > max_len:
            final.append(chunk[:max_len])
            chunk = chunk[max_len:]
        final.append(chunk)
    return final


def send_message(text: str, reply_markup: dict | None = None) -> dict:
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup

    response = requests.post(_api_url("sendMessage"), json=payload, timeout=10)
    response.raise_for_status()
    return response.json()


def send_letter(job: dict, draft: str) -> list[dict]:
    header = f"Letter draft ready -- {job.get('title')} at {job.get('company')}\n\n"
    return [send_message(chunk) for chunk in _chunk_text(header + draft)]


def send_approval_request(job: dict) -> dict:
    reply_markup = {
        "inline_keyboard": [[
            {"text": "Yes, write the letter", "callback_data": f"approve:{job['id']}"},
            {"text": "No", "callback_data": f"reject:{job['id']}"},
        ]]
    }
    return send_message(build_approval_request_text(job), reply_markup=reply_markup)


def get_updates(offset: int | None = None) -> list[dict]:
    params = {"timeout": 0}
    if offset is not None:
        params["offset"] = offset

    response = requests.get(_api_url("getUpdates"), params=params, timeout=10)
    response.raise_for_status()
    return response.json().get("result", [])


def answer_callback_query(callback_query_id: str, text: str = "") -> dict:
    response = requests.post(
        _api_url("answerCallbackQuery"),
        json={"callback_query_id": callback_query_id, "text": text},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def edit_message_text(chat_id: int, message_id: int, text: str) -> dict:
    response = requests.post(
        _api_url("editMessageText"),
        json={"chat_id": chat_id, "message_id": message_id, "text": text},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    mock_job = {
        "title": "Director Digital Sales Benelux",
        "company": "Mock Retail Group",
        "location": "Amsterdam, Netherlands",
        "relevance_score": 0.85,
        "url": "https://example.com/vacature/123",
    }
    result = send_approval_request(mock_job)
    print(result)
