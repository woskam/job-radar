import os
import sqlite3

import requests

from notify.telegram_bot import answer_callback_query, edit_message_text, get_updates

OFFSET_KEY = "telegram_update_offset"


def _from_owner(chat: dict | None) -> bool:
    # In practice a stranger can't press these buttons today -- this bot
    # only ever posts into your own chat, so nobody else sees them. This is
    # the one-line defence-in-depth for the day the bot token leaks or ends
    # up added to a group: a callback/reply is only ever acted on if it
    # actually came from the configured owner chat, since an approval here
    # is what triggers a paid Claude call.
    owner_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    return bool(chat and owner_chat_id and str(chat.get("id")) == str(owner_chat_id))


def _try(fn, *args) -> None:
    # Best-effort: confirming/editing a Telegram message must never crash the
    # whole batch -- e.g. a callback that's too old/already answered returns a
    # 400, but the job's own status has already been updated correctly by then.
    try:
        fn(*args)
    except requests.HTTPError:
        pass


def _get_offset(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT value FROM app_state WHERE key = ?", (OFFSET_KEY,)).fetchone()
    return int(row["value"]) + 1 if row else None


def _save_offset(conn: sqlite3.Connection, update_id: int) -> None:
    conn.execute(
        "INSERT INTO app_state (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (OFFSET_KEY, str(update_id)),
    )
    conn.commit()


def _handle_callback(conn: sqlite3.Connection, callback: dict) -> bool:
    if not _from_owner((callback.get("message") or {}).get("chat")):
        return False

    action, _, job_id_str = callback.get("data", "").partition(":")
    if action not in ("approve", "reject") or not job_id_str.isdigit():
        return False
    job_id = int(job_id_str)

    row = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not row or row["status"] != "pending_approval":
        _try(answer_callback_query, callback["id"], "Already processed.")
        return False

    if action == "approve":
        conn.execute("UPDATE jobs SET status = 'approved' WHERE id = ?", (job_id,))
    else:
        # rejected_reason stays empty -- a reply to this message fills it in
        # later (see _handle_reply), but the rejection itself doesn't wait on that.
        conn.execute(
            "UPDATE jobs SET status = 'rejected', rejected_at = CURRENT_TIMESTAMP, "
            "rejected_stage = 'approval', rejected_reason = NULL WHERE id = ?",
            (job_id,),
        )
    conn.commit()

    _try(answer_callback_query, callback["id"], "Approved" if action == "approve" else "Rejected")

    message = callback.get("message") or {}
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")
    if chat_id and message_id:
        if action == "approve":
            label = "Approved -- writing the letter now."
        else:
            label = "Rejected. Reply to this message with a reason if you want to note one (optional)."
        _try(edit_message_text, chat_id, message_id, f"{message.get('text', '')}\n\n{label}")

    return True


def _handle_reply(conn: sqlite3.Connection, message: dict) -> bool:
    """
    Links a plain reply message back to the job via the original approval
    request's stored telegram_message_id:
    - job is still 'pending_approval' -> the reply counts as a rejection with a
      reason (so you can skip the 'No' button too)
    - job is already 'rejected' without a reason -> the reason gets filled in
    - otherwise (already processed further) -> ignored
    """
    if not _from_owner(message.get("chat")):
        return False

    reply_to = message.get("reply_to_message")
    reason = (message.get("text") or "").strip()
    if not reply_to or not reason:
        return False

    row = conn.execute(
        "SELECT id, status FROM jobs WHERE telegram_message_id = ?", (reply_to["message_id"],)
    ).fetchone()
    if not row:
        return False

    if row["status"] == "pending_approval":
        conn.execute(
            "UPDATE jobs SET status = 'rejected', rejected_at = CURRENT_TIMESTAMP, "
            "rejected_stage = 'approval', rejected_reason = ? WHERE id = ?",
            (reason, row["id"]),
        )
        conn.commit()
        return True

    if row["status"] == "rejected":
        cursor = conn.execute(
            "UPDATE jobs SET rejected_reason = ? WHERE id = ? AND rejected_reason IS NULL",
            (reason, row["id"]),
        )
        conn.commit()
        return cursor.rowcount > 0

    return False


def process_telegram_approvals(conn: sqlite3.Connection) -> int:
    """
    Processes Approve/Reject button clicks and reply messages (rejection
    reasons) that have come in over Telegram since the previous poll. Runs as
    its own fast cycle (see approval_worker.py), decoupled from the slow
    scrape/score run in scheduler.py.
    """
    updates = get_updates(offset=_get_offset(conn))

    processed = 0
    max_update_id = None
    for update in updates:
        max_update_id = update["update_id"]

        callback = update.get("callback_query")
        if callback:
            if _handle_callback(conn, callback):
                processed += 1
            continue

        message = update.get("message")
        if message and _handle_reply(conn, message):
            processed += 1

    if max_update_id is not None:
        _save_offset(conn, max_update_id)

    return processed
