#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Send the one message that request C-0011 permits. Nothing else.

The recipient, the body path and the claim id come from the workflow's env
block, where they are constants in a public file — not from dispatch inputs.
See .github/workflows/send-one-email.yml for why.

Dependency-free: stdlib only, like everything else in this repository.

Two providers are supported because the choice depends on a fact only my
operator knows — whether she owns a domain. Resend's own documentation says
"You must add and verify at least one domain to send emails with Resend", so
without a domain that route is closed; SendGrid's Single Sender Verification
verifies one address instead, at the cost of requiring a physical mailing
address. Whichever secret is present is the one used. If both are present the
script stops rather than guessing, because guessing which credential to spend
is not a decision a script should make silently.
"""

import json
import os
import sys
import urllib.error
import urllib.request

TO = os.environ["TO"]
BODY_FILE = os.environ["BODY_FILE"]
FROM = os.environ.get("MAIL_FROM", "").strip()
REPLY_TO = os.environ.get("MAIL_REPLY_TO", "").strip()
# 表示名は **秘密ではない。だから公開されたコード側に置く。**
# 受信者が最初に見る1行がこれで、本文を読む前に「相手が何か」を伝える。
# 内容にあたるものを secret に隠すと、何を名乗って送ったのかが後から誰にも確かめられない。
# 括弧や引用符を避けてあるのは、表示名の quoting で1回きりの送信を落とさないため。
FROM_NAME = os.environ.get("MAIL_FROM_NAME", "").strip()
SENDGRID = os.environ.get("SENDGRID_API_KEY", "").strip()
RESEND = os.environ.get("RESEND_API_KEY", "").strip()


def die(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def split_subject(text):
    """The first line is 'Subject: ...'; the rest is the body."""
    head, _, rest = text.partition("\n")
    if not head.lower().startswith("subject:"):
        die("the body file must begin with a 'Subject:' line")
    return head.split(":", 1)[1].strip(), rest.lstrip("\n")


# セッション41 で足した。**これが無くて、承認された1通が落ちた。**
#
#   User-Agent 無し（Python-urllib/3.x） → 403 / error code: 1010（Cloudflare。Resend に届かない）
#   この文字列                            → 401 missing_api_key（Resend 本体が答えた）
#
# 同じランナー・同じ POST・同じ本文・資格情報なしで、**違いは User-Agent だけ**。
# 資格情報を一切持たない probe（.github/workflows/probe-post.yml）で2回測って確定した。
#
# **これは偽装ではない。** read-from-runner が「UA を偽ってブラウザのふりをするのはしない」と
# 決めていて、それはそのまま守る。ここでやっているのは逆で、**何も名乗らない既定値をやめて、**
# **自分が誰でどこに記録があるかを名乗る。** 名乗るほうが、名乗らないより正直。
#
# ★ なぜ落としたか：read-from-runner は最初からこの UA を持っていた。**私は送信側に写さなかった。**
# セッション28 の「検査を足すことと、その検査が走る場所を全部直すことは別の作業だった」と同じ形。
USER_AGENT = "n0-agent (github.com/nemuprojectofficial-glitch/n0-public)"


def post(url, payload, headers):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json",
                 "User-Agent": USER_AGENT, **headers})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")[:2000]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:2000]
    except urllib.error.URLError as e:
        # 接続そのものが立たなかった場合（DNS・遮断・切断）。
        # traceback を出すと「送れたのか送れなかったのか」が読む側に伝わらない。
        # **届いていないことだけは確かなので、0 を返して落とす。**
        return 0, f"connection failed: {e.reason}"


def main():
    if SENDGRID and RESEND:
        die("both SENDGRID_API_KEY and RESEND_API_KEY are set. "
            "Remove one; this script will not choose which credential to spend.")
    if not SENDGRID and not RESEND:
        die("no provider secret is set. Nothing sent.\n"
            "Set exactly one of SENDGRID_API_KEY or RESEND_API_KEY, plus MAIL_FROM.")
    if not FROM:
        die("MAIL_FROM is not set. It must be an address at the verified sending domain. Nothing sent.")
    # ★ セッション34 で足した。**無いと、返事が宙に消える。**
    #
    # C-0016 が可になり、送信元は「既存ドメインのサブドメイン」になった。
    # **そのサブドメインに受信箱は無い。** MX を置かないのだから当然で、置かないことが
    # 「既存プロジェクトのメールに触らない」という約束の中身でもある。
    #
    # すると、受け取った人が「返信」を押したとき、宛先は存在しないアドレスになり、
    # **返信はバウンスする。** そして私の側から見える形は——
    #
    #     返信が来ない。
    #
    # C-0011 が確かめようとしているのは、まさに「返事が来ないこと」の意味である。
    # **返信できない経路で「返事が来なかった」を観測しても、それは相手について何も言っていない。**
    # 実験そのものが、送る前から壊れている。
    #
    # だから Reply-To は任意ではなく必須にする。無ければ送らない。
    if not REPLY_TO:
        die("MAIL_REPLY_TO is not set. Nothing sent.\n"
            "The sending subdomain has no mailbox, so a reply to the From address would bounce —\n"
            "and a bounced reply looks exactly like no reply, which is the one thing this message\n"
            "exists to measure. Set MAIL_REPLY_TO to an address that is actually read.")

    # MAIL_FROM は素のアドレスで置いてもらう（例：agent@…）。表示名はここで付ける。
    # 既に "Name <addr>" の形で入っていれば、そのまま使う（二重に包まない）。
    sender = FROM if "<" in FROM else (f"{FROM_NAME} <{FROM}>" if FROM_NAME else FROM)

    subject, body = split_subject(open(BODY_FILE, encoding="utf-8").read())
    print(f"provider: {'SendGrid' if SENDGRID else 'Resend'}")
    # MAIL_FROM は secret なので、この行は公開ログ上では *** に伏せられる。
    # 送信ドメインはあやの既存プロジェクトのドメインの下にあり、**公開ログへ出すことは**
    # **C-0016 が許した「受信者1人に見せること」より広い。** 伏せられるのは都合がよい。
    print(f"from    : {sender}")
    print(f"from-name(公開): {FROM_NAME or '(なし)'}")
    print(f"reply-to: {REPLY_TO}")
    print(f"to      : {TO}")
    print(f"subject : {subject}")
    print(f"body    : {len(body)} characters")

    if SENDGRID:
        status, text = post(
            "https://api.sendgrid.com/v3/mail/send",
            {"personalizations": [{"to": [{"email": TO}]}],
             "from": {"email": sender},
             "reply_to": {"email": REPLY_TO},
             "subject": subject,
             "content": [{"type": "text/plain", "value": body}]},
            {"Authorization": f"Bearer {SENDGRID}"})
        ok = status == 202
    else:
        status, text = post(
            "https://api.resend.com/emails",
            # reply_to はペイロードのフィールド名。Resend の API リファレンスの原文で確認した
            # （"the payload for from, subject, and reply_to take precedence…"・2026-09-11 実測）。
            {"from": sender, "to": [TO], "reply_to": REPLY_TO,
             "subject": subject, "text": body},
            {"Authorization": f"Bearer {RESEND}"})
        ok = status in (200, 201)

    print(f"status  : {status}")
    print(f"response: {text}")
    if not ok:
        die("the provider did not accept the message. Nothing was delivered.")

    print()
    print("Sent. Now write the row in 監査/external.jsonl (claim_id C-0011) — "
          "after the act, never before.")
    print("C-0011 permits one message. There is no second one without a new request.")


if __name__ == "__main__":
    main()
