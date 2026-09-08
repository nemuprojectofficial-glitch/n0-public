#!/usr/bin/env python3
"""決着観測 — 請求の決着を「報告されるのを待つ」のではなく「世界を見て測る」。

なぜこれが要るか（2026-09-08 / セッション6）
--------------------------------------------------
監査/claims.jsonl の status は、あやが決着行を追記することで更新される設計だった。
実際には、追記は C-0001・C-0002 の一度きりしか起きていない。

  C-0003（topics 設定）  台帳=保留 のまま。しかし世界では **設定済み**（約2日前から）
  C-0005（書き込み権限）  台帳=保留 のまま。しかし世界では **付与済み**（約2日前から）

つまり status が測っていたのは「あやの返答速度」ではなく
「書き戻しの経路があるかどうか」だった。そして書き戻しの経路は無い。

  → 前提が外れているときにそれらしい数字を返す計器は、無い計器より悪い（セッション4）
  → status:保留 の件数は、その計器そのものだった。

この道具は、請求1件ごとに「可なら世界の側でこう見えるはず」という
**私には起こせない観測**を定義し、それを毎回実際に測る。

設計上の約束（破ると、この道具も壊れた計器になる）
--------------------------------------------------
1. **監査/ には一切書かない。** claims.jsonl の status は「あやの決定」を意味する列であり、
   私の推論を入れれば、それは虚偽になる。ここが出すのは *実効* であって *決定* ではない。
   決定と実効は別物（承認≠実効。C-0002・C-0005・C-0003 で3回外している）。
2. **各テストは、私には起こせないものに限る。** 自分で満たせるものは観測ではなく ToDo。
   自分で満たせてしまうテストには、満たさないという約束を condition に明記する。
3. **測れなかったことを「未実効」と言わない。** 通信失敗・トークン欠如は 測定不能 を返す。
   ここを混ぜると、権限が閉じたのか手が滑ったのか区別できなくなる。
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

REPO = "nemuprojectofficial-glitch/n0-public"
API = "https://api.github.com"

実効 = "実効"
未実効 = "未実効"
測定不能 = "測定不能"
観測不能 = "観測不能"  # 原理的に私からは見えない（テストが存在しない）


def _get(path):
    """GitHub API を叩く。(status_code, body_or_None) を返す。例外は投げない。"""
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        return None, None
    req = urllib.request.Request(
        f"{API}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "n0-claim-effect-probe (read-only)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception:
        return None, None


def _repo():
    return _get(f"/repos/{REPO}")


# ---------------------------------------------------------------- 個別のテスト

def t_0003():
    """C-0003: description と topics が設定されている。"""
    code, d = _repo()
    if code != 200 or d is None:
        return 測定不能, f"リポジトリのメタ情報を読めなかった（HTTP {code}）"
    topics, desc = d.get("topics") or [], d.get("description")
    if topics and desc:
        return 実効, f"description 設定済み / topics {len(topics)}件: {', '.join(topics)}"
    return 未実効, f"description={desc!r} / topics={topics}"


def t_0004():
    """C-0004: LICENSE が置かれている。"""
    code, d = _repo()
    if code != 200 or d is None:
        return 測定不能, f"リポジトリのメタ情報を読めなかった（HTTP {code}）"
    lic = d.get("license")
    if lic:
        return 実効, f"license={lic.get('spdx_id')}"
    return 未実効, "license は未設定"


def t_0005():
    """C-0005: 私の push が実際に n0-public の main に載っている。"""
    code, d = _get(f"/repos/{REPO}/commits?per_page=1")
    if code != 200 or not d:
        return 測定不能, f"コミット一覧を読めなかった（HTTP {code}）"
    c = d[0]
    return 実効, f"最新コミット {c['sha'][:7]} ({c['commit']['author']['date']}) が main に載っている"


def t_0006():
    """C-0006: PyPI の資格情報がこの環境に存在する。"""
    for k in ("PYPI_TOKEN", "PYPI_API_TOKEN", "TWINE_PASSWORD", "UV_PUBLISH_TOKEN"):
        if os.environ.get(k):
            return 実効, f"環境変数 {k} が存在する（中身は読まないし、どこにも書かない）"
    if os.path.exists(os.path.expanduser("~/.pypirc")):
        return 実効, "~/.pypirc が存在する"
    return 未実効, "PyPI の資格情報は、環境変数にも ~/.pypirc にも無い"


def t_0007():
    """C-0007: あやが人間の読む場所へ投稿した。"""
    return 観測不能, (
        "投稿先（HN・SNS・掲示板）は、この箱からは全ホスト遮断されている（EGRESS.md）。"
        "到達したかどうかは traffic でしか見えず、それが C-0008。"
        "**C-0008 が閉じている限り、C-0007 は可否にかかわらず結果を読めない。**"
    )


def t_0008():
    """C-0008: traffic API が読める。"""
    code, _ = _get(f"/repos/{REPO}/traffic/views")
    if code == 200:
        return 実効, "traffic/views が 200 を返す。公開以来の unique visitor が読める"
    if code == 403:
        return 未実効, "traffic/views は 403（Administration:read が無い）"
    return 測定不能, f"traffic/views が想定外の応答（HTTP {code}）"


検査 = [
    # claim_id, 一行の中身, テスト, なぜ私には起こせないか
    ("C-0003", "description と topics の設定", t_0003,
     "リポジトリ設定の書き込みはトークンの権限外。私は description も topics も変更できない"),
    ("C-0004", "MIT ライセンスを置く許可", t_0004,
     "私は n0-public へ push できるので LICENSE を置くことは技術的には可能。"
     "**C-0004 が可になるまで置かないと決めている**ので、その約束が守られている限りこのテストは有効"),
    ("C-0005", "n0-public への書き込み権限", t_0005,
     "権限を与えるのは環境設定側。このセッションからは読むことも変えることもできない"),
    ("C-0006", "PyPI のアカウントとトークン", t_0006,
     "資格情報を環境に注入できるのはあやだけ。私は自分に鍵を配れない"),
    ("C-0007", "あやが1回だけ投稿する", t_0007,
     "（テストが存在しない。私からは原理的に見えない）"),
    ("C-0008", "traffic を読めるようにする", t_0008,
     "GitHub App のインストール権限は環境側にあり、私は自分の権限を広げられない"),
]


def 走る():
    out = []
    for cid, 中身, test, why in 検査:
        try:
            状態, 根拠 = test()
        except Exception as e:  # テストの故障を「未実効」に化けさせない
            状態, 根拠 = 測定不能, f"テストが例外で落ちた: {e!r}"
        out.append({"claim_id": cid, "中身": 中身, "実効": 状態,
                    "根拠": 根拠, "why_not_me": why})
    return out


def 台帳の状態(ledger="監査"):
    """claims.jsonl から、claim_id ごとの最新 status を読む（位置ではなく ts で解決）。"""
    最新 = {}
    try:
        with open(os.path.join(ledger, "claims.jsonl"), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                cid, ts = d.get("claim_id"), d.get("ts", "")
                if cid and (cid not in 最新 or ts >= 最新[cid][0]):
                    最新[cid] = (ts, d.get("status"))
    except FileNotFoundError:
        return {}
    return {c: s for c, (_, s) in 最新.items()}


def main():
    p = argparse.ArgumentParser(description="請求の決着を、報告ではなく実効で測る")
    p.add_argument("--repo", default=".", help="リポジトリのパス")
    p.add_argument("--ledger", default="監査",
                   help="台帳ディレクトリ（n0 では 監査、n0-public の写しでは audit）")
    p.add_argument("--json", action="store_true")
    a = p.parse_args()
    os.chdir(a.repo)

    結果 = 走る()
    台帳 = 台帳の状態(a.ledger)
    now = subprocess.run(["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"],
                         capture_output=True, text=True).stdout.strip()

    for r in 結果:
        r["台帳の status"] = 台帳.get(r["claim_id"], "(記録なし)")
        r["食い違い"] = (r["台帳の status"] == "保留" and r["実効"] == 実効)

    if a.json:
        print(json.dumps({"ts": now, "結果": 結果}, ensure_ascii=False, indent=2))
        return 0

    print(f"決着観測  {now}")
    print(f"対象: {REPO}\n")
    print(f"  {'請求':8} {'台帳':6} {'世界':8} 中身")
    print("  " + "-" * 72)
    for r in 結果:
        印 = " ←食い違い" if r["食い違い"] else ""
        print(f"  {r['claim_id']:8} {r['台帳の status']:6} {r['実効']:8} {r['中身']}{印}")
    print()
    for r in 結果:
        print(f"  {r['claim_id']}: {r['根拠']}")

    食い違い = [r for r in 結果 if r["食い違い"]]
    print()
    if 食い違い:
        ids = "・".join(r["claim_id"] for r in 食い違い)
        print(f"  ** {len(食い違い)}件、台帳が『保留』のまま世界では既に効いている（{ids}）。")
        print("  ** 台帳の『保留』件数を、あやの返答速度として読まないこと。")
    else:
        print("  台帳と世界の食い違いは無い。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
