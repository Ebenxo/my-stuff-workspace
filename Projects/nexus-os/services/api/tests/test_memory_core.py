"""Pure parts of memory: sensitivity guard, embedder, ranking, importance, compression, context cutting."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.agents.context import cost, cut_to
from app.memory import compressor, sensitivity
from app.memory.embedder import HashingEmbedder, cosine, words
from app.memory.scoring import MIN_SEMANTIC, bm25, importance_for, rank, recency
from app.schemas.memory import MemoryItemOut, MemorySource

NOW = datetime(2026, 9, 29, 12, tzinfo=UTC)
E = HashingEmbedder()


def item(content: str, **kw: object) -> MemoryItemOut:
    data: dict[str, object] = {
        "id": f"mem_{abs(hash(content)) % 10**8:08d}",
        "scope": "project",
        "project_id": "proj_1",
        "content": content,
        "summary": "",
        "importance": 0.5,
        "source": MemorySource(kind="agent"),
        "tags": [],
        "status": "active",
        "content_hash": "h",
        "access_count": 0,
        "last_accessed_at": None,
        "merged_into": None,
        "created_at": NOW,
        "updated_at": NOW,
    }
    data.update(kw)
    return MemoryItemOut.model_validate(data)


# ---------------------------------------------------------------- sensitivity guard


@pytest.mark.parametrize(
    ("text", "category"),
    [
        ("our key is sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123", "API key"),
        ("password = hunter2hunter2", "password or secret"),
        ("-----BEGIN RSA PRIVATE KEY-----\nMIIEow\n-----END RSA PRIVATE KEY-----", "private key"),
        ("Authorization: Bearer abcdefghijklmnop.qrstuvwx", "access token"),
        ("AKIAIOSFODNN7EXAMPLE is the deploy user", "cloud credential"),
        ("card 4111 1111 1111 1111 exp 12/29", "payment card number"),
        ("SSN 123-45-6789 on file", "national identity number"),
        ("NI number AB 12 34 56 C", "national identity number"),
        ("pay to GB82 WEST 1234 5698 7654 32", "bank account number"),
        ("AccountKey=abcdefghijklmnopqrstuvwxyz0123456789ABCD==", "cloud credential"),
    ],
)
def test_sensitive_content_is_recognised_by_category(text: str, category: str) -> None:
    found = sensitivity.scan(text)
    assert category in found
    # the explanation names the category, never the matched value
    explained = sensitivity.explain(found)
    assert category in explained and "hunter2" not in explained and "4111" not in explained


@pytest.mark.parametrize(
    "text",
    [
        "The client prefers British spelling and a friendly tone.",
        "Invoice 2026-09-29 totalled 1,250.00 across 14 line items.",
        "Order number 4111 1111 1111 1112 is not a real card (fails Luhn).",
        "Call +44 20 7946 0958 before noon.",
        "The IBAN field format is GB00 XXXX 0000 0000 0000 00.",
        "Use the token budget of 200000 per run.",
    ],
)
def test_ordinary_notes_are_not_flagged(text: str) -> None:
    assert sensitivity.scan(text) == []


# ---------------------------------------------------------------- embedder


def test_embedder_is_deterministic_normalised_and_lexically_meaningful() -> None:
    a = E.embed("Quarterly invoices are sent on the first Monday")
    assert a == HashingEmbedder().embed("Quarterly invoices are sent on the first Monday")
    assert len(a) == 256 and abs(sum(v * v for v in a) - 1.0) < 1e-3
    near = cosine(a, E.embed("When are the quarterly invoice emails sent?"))
    far = cosine(a, E.embed("The logo uses a teal and coral palette"))
    assert near > 0.3 > far
    assert E.embed("") == [0.0] * 256 and cosine(E.embed(""), a) == 0.0
    # stopwords are ignored and simple plurals fold together
    assert words("The invoices of the clients") == ["invoice", "client"]


def test_bm25_prefers_rare_matching_terms() -> None:
    docs = [words("teal palette logo"), words("invoice schedule monday"), words("invoice totals")]
    scores = bm25(words("monday invoice"), docs)
    assert scores[1] > scores[2] > scores[0] == 0.0


# ---------------------------------------------------------------- ranking


def test_rank_orders_by_relevance_and_explains_the_score() -> None:
    q = "What spelling does the client prefer?"
    cands = [
        item("The client prefers British spelling in all documents."),
        item("Deliverables go in the artifacts folder as Markdown."),
        item("Spelling: use -ise endings, never -ize.", tags=["spelling"]),
        item("Budget for the website is 4000 pounds."),
    ]
    ranked = rank(q, E.embed(q), [(c, E.embed(c.content)) for c in cands], now=NOW)
    ids = [r.item.content for r in ranked]
    assert ids[0].startswith("The client prefers British spelling")
    assert "Budget for the website is 4000 pounds." not in ids  # unrelated: excluded, not just ranked low
    top = ranked[0].score
    assert top.semantic > MIN_SEMANTIC and top.keyword == 1.0 and 0 < top.total <= 1
    tagged = next(r for r in ranked if r.item.tags == ["spelling"])
    assert tagged.score.task == 0.5  # its tag names a word in the query


def test_importance_and_recency_break_ties_but_never_make_irrelevant_items_relevant() -> None:
    q = "deployment checklist"
    old = item("Deployment checklist: run tests, tag release.", updated_at=NOW - timedelta(days=90))
    new = item("Deployment checklist: run tests, tag release!", updated_at=NOW)
    pinned_unrelated = item("The office cat is called Biscuit.", importance=1.0)
    ranked = rank(q, E.embed(q), [(c, E.embed(c.content)) for c in (old, new, pinned_unrelated)], now=NOW)
    assert [r.item.content for r in ranked] == [new.content, old.content]
    assert recency(new, NOW) == 1.0 and recency(old, NOW) < 0.1
    # same objective ranks higher than an equally relevant item from elsewhere
    mine = item(
        "Deployment checklist for this objective", source=MemorySource(kind="agent", objective_id="obj_1")
    )
    other = item(
        "Deployment checklist for this objective.", source=MemorySource(kind="agent", objective_id="obj_2")
    )
    r = rank(
        q,
        E.embed(q),
        [(other, E.embed(other.content)), (mine, E.embed(mine.content))],
        now=NOW,
        objective_id="obj_1",
    )
    assert r[0].item is mine and r[0].score.task == 1.0


def test_items_without_vectors_can_still_match_on_keywords() -> None:
    q = "invoice schedule"
    ranked = rank(q, E.embed(q), [(item("Invoice schedule: first Monday"), None)], now=NOW)
    assert len(ranked) == 1 and ranked[0].score.semantic == 0.0 and ranked[0].score.keyword == 1.0


def test_importance_bands_stop_agents_promoting_their_own_memories() -> None:
    assert importance_for("user") == 0.8
    assert importance_for("agent") == 0.5
    assert importance_for("agent", 1.0) == 0.7  # clamped to the band
    assert importance_for("agent", 0.0) == 0.3
    assert importance_for("agent", 0.9, tainted=True) == 0.4  # written after reading untrusted content
    assert importance_for("objective") == 0.4


# ---------------------------------------------------------------- compression


def test_compression_groups_related_old_notes_and_keeps_central_sentences() -> None:
    notes = [
        item("Invoices are sent on the first Monday. The client pays within 14 days."),
        item("Invoice reminders go out after 14 days. The client pays by bank transfer."),
        item("Invoices use the blue template. The client asked for PDF invoices."),
        item("The logo is teal."),
    ]
    groups = compressor.group([(n, E.embed(n.content)) for n in notes])
    assert len(groups) == 1 and len(groups[0].items) == 3
    summary = compressor.summarise(groups[0])
    assert summary.startswith("Summary of 3 older notes:") and "The logo is teal." not in summary
    assert len(summary) <= compressor.SUMMARY_CHARS + 40
    # tags also group items, even when their wording differs
    tagged = [
        item(t, tags=["travel"])
        for t in ("Flights via Lisbon.", "Hotel near the station.", "Trains are cheaper.")
    ]
    assert len(compressor.group([(t, E.embed(t.content)) for t in tagged])) == 1
    assert compressor.group([(n, E.embed(n.content)) for n in notes[:2]]) == []  # too few to compress


# ---------------------------------------------------------------- context cutting


def test_cut_to_ends_at_a_sentence_and_says_what_was_omitted() -> None:
    text = " ".join(f"Sentence number {i} has some words in it." for i in range(400))
    cut = cut_to(text, 300)
    assert cost(cut) <= 300 + 40
    body, note = cut.rsplit("\n", 1)
    assert body.endswith(".") and note.startswith("…[") and "characters omitted" in note
    assert cut_to("short", 300) == "short"
