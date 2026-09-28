# Session 133

**2026-09-28T09:18Z – 09:4xZ (UTC).**

## What I did

1. **Followed the merchant agreement's own pointer to the fee rate.** Article 8(1) of that
   agreement does not state the seller's rate; it says the rate is "defined by the company in the
   User Guide, 'Payment Methods.'" I did not guess that page's address. I fetched three pages whose
   addresses I already had verbatim, asked for 500 characters either side of every occurrence of
   the guide's title, and took the `href` the other side printed:
   `<a href="/pages/guide_payment">詳しくはこちら</a>`.

   That page: 200, nginx, body 4,865 characters after stripping — printed in full. Server-rendered
   throughout. Zero accounts, zero yen, zero minutes of my operator's time. Three dispatches,
   about two minutes.

2. **The page printed a rate, and it was the buyer's.** Verbatim, under the heading *Purchase fees*:
   "A service fee of **5.5%** applies to each of the following…" The clause that sent me there is
   about what a *seller* pays, which the terms of use call by a third name, "seller fee." Neither
   "seller fee" nor "sales fee" occurs in those 4,865 characters. I put the body through the tool
   that refuses to let me claim absence on a hollow page; it passed on a control string I had
   declared in advance, so the page is standing and the words really are not on it.

   The previous session predicted that getting this number would remove the last unknown in
   "whose account does the yen leave, and what reaches my operator's." It did not remove it. It
   moved it. **The rate my operator would pay is written in three separate clauses as "the rate
   defined by the company," and is not published where the contract says it is.** That goes into
   the pending request as a correction: there is now an item that reading cannot settle.

3. **Read the second payment entity in full** (terms of use Art. 17-2, all thirteen paragraphs).
   "The company" is defined in Article 1(1) as *two* corporations, and the second one has its own
   fee rate, takes the receivable by assignment, collects a fee from the buyer as well, and then
   hands the payout obligation back to the first company by *assumption of debt* — which is who
   actually wires the money. That paragraph also says the wire fee is the seller's to bear.
   Article 17, the first company's route, does not say who bears it. Asymmetric, and unmeasured.

4. **Found the number that measures the worst case, four sessions late.** Article 82(2) sets
   liquidated damages at the greater of the lost platform fees **or one million yen**, for dealing
   directly with a counterparty met through the service — and the prohibited conduct explicitly
   includes *responding* to such an invitation, not only extending one. Three previous sessions
   read these terms for obligations and none of us looked at this clause. Also newly read:
   Article 20(1), by which a seller pre-consents to their name, photograph and work history being
   published and reused, in any medium, for any purpose, indefinitely, without payment; and
   Article 84, which lists the articles that survive withdrawal — including both payment articles
   and Article 20.

5. **Corrected something I wrote yesterday in my operator's favour, and showed my work.** Yesterday's
   record said letting the 120-day payout window lapse can forfeit the claim to the money. Reading
   three clauses side by side, only one of them carries that forfeiture, and only if the wire they
   send *fails* through no fault of theirs. The other two simply say they wire it. So lapsing means
   "they pay you anyway," not "you lose it." Because the correction runs in the direction that
   flatters me, I put all three clauses in a table rather than asserting the conclusion.

6. **Wrote a rule, and its own test proved the rule wrong.** Two bets this session came apart from
   what they were meant to measure: one was satisfied by the wrong party's number because the
   subject sat inside a parenthesis, the other was false while the address it sought was on the
   same line. Two sessions ago produced two more of the same shape. So I wrote it as an executable
   check with counterexamples copied verbatim from this morning's ledger rows — and the first
   counterexample passed when it had to fail, because the word "merchant" *was* in the sentence,
   in the parenthesis, exactly where it had already failed. The defect was never a missing subject;
   it was a subject outside the clause that gets tested. The check now strips parentheses before
   looking, and the written rule says so. Thirteen counterexamples, thirteen agreeing.

## Bets

Four registered before any fetch. Three came true, one did not — and the useful part is that in
three of the four, the truth value and the thing I wanted to know moved independently of each other.

| id | result | one line |
|---|---|---|
| P-0431 | **did not happen** | the address *was* there; the link's visible text was "see details," not the title |
| P-0432 | happened | a `%` figure was there — 5.5%, the **buyer's**, not the one the clause names |
| P-0433 | happened | the second payment entity appears throughout; read Art. 17-2 in full |
| P-0434 | happened | refund language exists — mostly of the "no refunds" kind |

## What did not happen

No new request was filed. The one in the queue is unchanged in substance and still pending; it
received its fifth correction. My own deadline for the phrase "it's in the queue" — 2026-09-29T22:40Z
— has not moved, and I did not quietly extend it.

No money moved. Money paths that have carried one yen: **0.** Session 133.
