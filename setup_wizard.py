#!/usr/bin/env python3
"""
Interactive first-time setup: walks through .env, profile.yaml, and your
CV/projects instead of five manual copy+edit steps. Safe to re-run -- each
step is skipped (with an option to redo it) if its target file already
exists.

Edits the copied template text directly (regex substitution on specific
placeholder lines), not a YAML parse+dump round-trip -- that would silently
throw away the explanatory comments in profile.example.yaml, which are the
whole reason hand-tuning it later stays easy.
"""
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    answer = input(f"{prompt}{suffix}: ").strip()
    return answer or default


def confirm(prompt: str, default_yes: bool = False) -> bool:
    suffix = "[Y/n]" if default_yes else "[y/N]"
    answer = input(f"{prompt} {suffix} ").strip().lower()
    if not answer:
        return default_yes
    return answer.startswith("y")


def _should_write(target: Path) -> bool:
    if not target.exists():
        return True
    return confirm(f"{target} already exists -- overwrite it?", default_yes=False)


def step_env() -> None:
    print("\n=== .env (API keys) ===")
    target = ROOT / ".env"
    if not _should_write(target):
        print("Skipped.")
        return

    text = (ROOT / ".env.example").read_text()

    print("Anthropic API key -- get one at https://console.anthropic.com/settings/keys")
    anthropic_key = ask("ANTHROPIC_API_KEY (leave blank to fill in later)")
    print("\nTelegram bot -- create one via @BotFather on Telegram to get a token,")
    print("then message your own bot once so it can message you back.")
    bot_token = ask("TELEGRAM_BOT_TOKEN (leave blank to fill in later)")
    chat_id = ask("TELEGRAM_CHAT_ID (leave blank to fill in later)")

    if anthropic_key:
        text = re.sub(r"^ANTHROPIC_API_KEY=.*$", f"ANTHROPIC_API_KEY={anthropic_key}", text, flags=re.MULTILINE)
    if bot_token:
        text = re.sub(r"^TELEGRAM_BOT_TOKEN=.*$", f"TELEGRAM_BOT_TOKEN={bot_token}", text, flags=re.MULTILINE)
    if chat_id:
        text = re.sub(r"^TELEGRAM_CHAT_ID=.*$", f"TELEGRAM_CHAT_ID={chat_id}", text, flags=re.MULTILINE)

    target.write_text(text)
    print(f"Wrote {target}.")

    if anthropic_key:
        validate_anthropic_key(anthropic_key)
    if bot_token:
        validate_telegram(bot_token, chat_id)


def validate_anthropic_key(key: str) -> None:
    try:
        from anthropic import Anthropic

        Anthropic(api_key=key).models.list(limit=1)
        print("Anthropic key: looks valid.")
    except Exception as e:
        print(f"Anthropic key: could not validate ({e}) -- double check it before relying on it.")


def validate_telegram(token: str, chat_id: str) -> None:
    import requests

    try:
        me = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10).json()
        if not me.get("ok"):
            print(f"Telegram bot token: not valid ({me.get('description')}).")
            return
        print(f"Telegram bot token: valid (@{me['result']['username']}).")
    except Exception as e:
        print(f"Telegram bot token: could not validate ({e}).")
        return

    if not chat_id:
        return
    try:
        chat = requests.get(
            f"https://api.telegram.org/bot{token}/getChat", params={"chat_id": chat_id}, timeout=10
        ).json()
        if chat.get("ok"):
            print(f"Telegram chat id: valid (chat with {chat['result'].get('first_name', chat_id)}).")
        else:
            print(
                f"Telegram chat id: not valid ({chat.get('description')}) -- "
                "make sure you've sent your bot at least one message first."
            )
    except Exception as e:
        print(f"Telegram chat id: could not validate ({e}).")


def step_profile() -> None:
    print("\n=== profile.yaml (keywords, location, sender details) ===")
    target = ROOT / "profile.yaml"
    if not _should_write(target):
        print("Skipped.")
        return

    text = (ROOT / "profile.example.yaml").read_text()

    print("Keywords to match in job titles, comma-separated (you can refine these later).")
    raw_keywords = ask('e.g. "director, senior manager, product manager"')
    if raw_keywords:
        keywords = [k.strip() for k in raw_keywords.split(",") if k.strip()]
        block = "keywords:\n" + "\n".join(f'  - "{k}"' for k in keywords) + "\n"
        text = re.sub(r"keywords:\n(?:  - .*\n)+", block, text, count=1)

    center = ask("City you're searching around", "Amsterdam")
    text = re.sub(r'center: "Amsterdam"', f'center: "{center}"', text, count=1)

    raw_cities = ask("Cities that count as 'home turf', comma-separated", center)
    cities = [c.strip() for c in raw_cities.split(",") if c.strip()]
    if cities:
        block = "  bonus_cities:\n" + "\n".join(f'    - "{c}"' for c in cities) + "\n"
        text = re.sub(r"  bonus_cities:\n(?:    - .*\n)+", block, text, count=1)

    print("\nSender details, shown on the letterhead of downloaded documents:")
    name = ask("Your name")
    address = ask("Your address (street, postal code, city)")
    email = ask("Your email")
    url = ask("Your website (optional)")
    if name:
        text = text.replace('name: "Your Name"', f'name: "{name}"', 1)
    if address:
        text = text.replace('address: "Your Street 1, 1234 AB Your City"', f'address: "{address}"', 1)
    if email:
        text = text.replace('email: "you@example.com"', f'email: "{email}"', 1)
    if url:
        text = text.replace('url: "www.yourwebsite.com"', f'url: "{url}"', 1)

    target.write_text(text)
    print(f"Wrote {target}.")
    print(
        "Fine-tune keyword_weights, netherlands_markers/foreign_markers, and "
        "scoring.exclude_title_keywords by hand later -- see README's 'Adding your own keywords'."
    )


def step_cv_and_projects() -> None:
    print("\n=== CV & projects ===")
    letters_dir = ROOT / "letters"
    copies = [
        (letters_dir / "cv.example.txt", letters_dir / "cv.txt"),
        (letters_dir / "cv_short.example.yaml", letters_dir / "cv_short.yaml"),
        (letters_dir / "projects.example.json", letters_dir / "projects.json"),
    ]
    for src, dst in copies:
        if _should_write(dst):
            shutil.copy(src, dst)
            print(f"Wrote {dst} (from {src.name}) -- edit it with your real details.")
        else:
            print(f"Skipped {dst}.")

    env_text = (ROOT / ".env").read_text() if (ROOT / ".env").exists() else ""
    key_match = re.search(r"^ANTHROPIC_API_KEY=(.+)$", env_text, re.MULTILINE)
    has_key = bool(key_match and key_match.group(1).strip())

    if not has_key:
        print(
            "\nNo ANTHROPIC_API_KEY found in .env, so skipping the option to have Claude convert "
            "a pasted CV -- edit the files above by hand, or add the key and re-run this step."
        )
        return

    if not confirm(
        "\nPaste your raw CV text and have Claude turn it into cv.txt's format "
        "(and propose projects.json entries)? This is a real, billed Claude API call.",
        default_yes=False,
    ):
        print("Skipped -- edit the copied template files by hand.")
        return

    print("Paste your CV text below. Finish with a line containing only END:")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "END":
            break
        lines.append(line)
    raw_cv = "\n".join(lines).strip()
    if not raw_cv:
        print("Nothing pasted -- skipping.")
        return

    convert_cv_with_claude(raw_cv, key_match.group(1).strip())


def convert_cv_with_claude(raw_cv: str, api_key: str) -> None:
    from anthropic import Anthropic

    letters_dir = ROOT / "letters"
    cv_template = (letters_dir / "cv.example.txt").read_text()
    projects_template = (letters_dir / "projects.example.json").read_text()

    prompt = f"""Here is a raw CV, pasted as plain text:

{raw_cv}

Rewrite it into exactly this structure (same section headers, same overall shape) -- \
stay factual, don't invent achievements, numbers, or projects that aren't in the source text:

{cv_template}

Then, separately, propose 2-4 entries for a projects.json file in exactly this schema, \
based on any project-like content in the source text (skip this if there's nothing to build \
real entries from -- don't invent projects):

{projects_template}

Output exactly two sections, nothing else, no commentary:
=== CV ===
<the rewritten CV as plain text>
=== PROJECTS_JSON ===
<the projects.json content, valid JSON, or [] if there's nothing to include>
"""

    from letters.llm import MAX_TOKENS, MODEL, reply_text

    print("Calling Claude...")
    try:
        response = Anthropic(api_key=api_key).messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        text = reply_text(response)
    except Exception as e:
        print(f"Claude call failed: {e} -- edit the copied template files by hand instead.")
        return

    cv_match = re.search(r"=== CV ===\s*(.*?)\s*=== PROJECTS_JSON ===\s*(.*)", text, re.DOTALL)
    if not cv_match:
        print("Couldn't parse Claude's response into the expected two sections -- printing it raw:")
        print(text)
        return

    cv_text, projects_json = cv_match.group(1).strip(), cv_match.group(2).strip()
    (letters_dir / "cv.txt").write_text(cv_text + "\n")
    print(f"Wrote {letters_dir / 'cv.txt'}.")

    import json

    try:
        json.loads(projects_json)
        (letters_dir / "projects.json").write_text(projects_json + "\n")
        print(f"Wrote {letters_dir / 'projects.json'}.")
    except json.JSONDecodeError:
        print("Claude's projects.json output wasn't valid JSON -- left projects.json untouched. Raw output:")
        print(projects_json)

    print("\nReview both files before trusting them in a real letter -- this is AI-generated from what you pasted.")


def main() -> None:
    print("Job Radar setup wizard\n" + "=" * 23)
    step_env()
    step_profile()
    step_cv_and_projects()

    print("\n=== Done ===")
    print("Next: dry-run everything first (safe, no API costs or real Telegram sends):")
    print("  ./run.sh")
    print("  ./run_approvals.sh")
    print("Once you're happy, set DRY_RUN=false and SCRAPE_LIVE=true in .env and run again for real.")
    print("See README.md for installing the systemd timers and running the dashboard.")


if __name__ == "__main__":
    main()
