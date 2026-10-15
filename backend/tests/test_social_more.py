"""Phase S3: profiles, pins, views, likers, link previews, polls, Poll → Debate, Daily Debate, explore, DMs."""
from __future__ import annotations

import io
import uuid
from datetime import timedelta

from sqlalchemy import select, update

from backend.app.db.session import SessionFactory
from backend.app.models import Post, PostPoll, User
from backend.app.services import link_preview

A = "/api/v1"


async def post(actor, text="Hello arena", **extra):
    r = await actor.post(f"{A}/posts", {"text": text, **extra})
    assert r.status_code == 201, r.text
    return r.json()


# ── Profiles, pins, views, likers ──────────────────────────────────────────


async def test_profile_extras_and_pinned_post(client, make_user):
    from PIL import Image
    alice = await make_user("alice")
    r = await alice.client.patch(f"{A}/me", json={"website": "provok.in", "location": "  Lucknow, India "},
                                 headers=alice.h)
    assert r.json()["website"] == "https://provok.in" and r.json()["location"] == "Lucknow, India"
    r = await alice.client.patch(f"{A}/me", json={"website": "not a url"}, headers=alice.h)
    assert r.status_code == 422
    buf = io.BytesIO()
    Image.new("RGB", (1200, 900), "navy").save(buf, format="JPEG")
    r = await alice.client.post(f"{A}/me/banner", files={"file": ("b.jpg", buf.getvalue(), "image/jpeg")}, headers=alice.h)
    assert r.status_code == 200 and r.json()["banner_url"].endswith(".webp")

    p = await post(alice, "pin me")
    assert (await alice.post(f"{A}/posts/{p['id']}/pin")).json()["pinned"] is True
    profile = (await client.get(f"{A}/users/alice")).json()
    assert profile["pinned"]["id"] == p["id"] and profile["banner_url"] and profile["website"] == "https://provok.in"
    listed = lambda: client.get(f"{A}/users/alice/posts")  # noqa: E731
    assert p["id"] not in [i["id"] for i in (await listed()).json()["items"]]  # shown once, on top
    bob = await make_user("bob")
    assert (await bob.post(f"{A}/posts/{p['id']}/pin")).status_code == 403
    await alice.client.delete(f"{A}/posts/{p['id']}/pin", headers=alice.h)
    assert (await client.get(f"{A}/users/alice")).json()["pinned"] is None
    assert p["id"] in [i["id"] for i in (await listed()).json()["items"]]


async def test_views_count_once_per_person_per_hour(client, make_user):
    alice, bob = await make_user("alice"), await make_user("bob")
    p = await post(alice)
    await alice.get(f"{A}/posts/{p['id']}")  # the author's own views don't count
    for _ in range(3):
        r = await bob.get(f"{A}/posts/{p['id']}")
    assert r.json()["post"]["counts"]["views"] == 1
    r = await client.get(f"{A}/posts/{p['id']}")  # signed out: counted by IP
    assert r.json()["post"]["counts"]["views"] == 2


async def test_likers_list(client, make_user):
    alice, bob, carol = await make_user("alice"), await make_user("bob"), await make_user("carol")
    p = await post(alice)
    await bob.post(f"{A}/posts/{p['id']}/like")
    await carol.post(f"{A}/posts/{p['id']}/like")
    names = [u["username"] for u in (await client.get(f"{A}/posts/{p['id']}/likes")).json()["items"]]
    assert names == ["carol", "bob"]
    await alice.post(f"{A}/users/carol/block")
    names = [u["username"] for u in (await alice.get(f"{A}/posts/{p['id']}/likes")).json()["items"]]
    assert names == ["bob"]


# ── Link previews ──────────────────────────────────────────────────────────

PAGE = """<html><head><title>Fallback</title>
<meta property="og:title" content="Chai &amp; Code" /><meta name="description" content="A blog about tea.">
<meta property="og:image" content="/img/cover.png"><meta property="og:site_name" content="Chai Blog">
</head><body>ignored</body></html>"""


def test_parse_preview():
    p = link_preview.parse_preview(PAGE, "https://example.com/post/1")
    assert p == {"url": "https://example.com/post/1", "title": "Chai & Code", "description": "A blog about tea.",
                 "image": "https://example.com/img/cover.png", "site": "Chai Blog"}
    assert link_preview.parse_preview("<html><head></head></html>", "https://x.com") is None
    bad = '<head><title>T</title><meta property="og:image" content="javascript:alert(1)"></head>'
    assert link_preview.parse_preview(bad, "https://x.com")["image"] is None
    assert link_preview.first_url("see https://example.com/a), ok") == "https://example.com/a"


async def test_link_preview_attaches_after_posting(client, make_user, jobs, monkeypatch):
    async def fake_fetch(url):
        return PAGE, url
    monkeypatch.setattr(link_preview, "fetch_html", fake_fetch)
    alice = await make_user("alice")
    p = await post(alice, "Read this https://example.com/post/1")
    assert "link_preview" in jobs.names()
    await jobs.run()
    lp = (await client.get(f"{A}/posts/{p['id']}")).json()["post"]["link_preview"]
    assert lp["title"] == "Chai & Code" and lp["site"] == "Chai Blog"


# ── Polls ──────────────────────────────────────────────────────────────────


async def test_polls_hide_results_until_you_vote(client, make_user):
    alice, bob, carol = await make_user("alice"), await make_user("bob"), await make_user("carol")
    p = await post(alice, "Best chai time?", poll=["Morning", "Evening", "Always"], poll_hours=24)
    assert [o["votes"] for o in p["poll"]["options"]] == [0, 0, 0]  # the author sees results
    before = (await bob.get(f"{A}/posts/{p['id']}")).json()["post"]["poll"]
    assert [o["votes"] for o in before["options"]] == [None, None, None] and before["viewer_vote"] is None
    r = await bob.post(f"{A}/posts/{p['id']}/vote", {"option": 2})
    assert r.json()["poll"]["viewer_vote"] == 2 and [o["votes"] for o in r.json()["poll"]["options"]] == [0, 0, 1]
    assert (await bob.post(f"{A}/posts/{p['id']}/vote", {"option": 0})).json()["error"]["code"] == "already_voted"
    assert (await carol.post(f"{A}/posts/{p['id']}/vote", {"option": 3})).status_code == 422

    async with SessionFactory() as db:  # end the poll
        await db.execute(update(PostPoll).where(PostPoll.post_id == uuid.UUID(p["id"]))
                         .values(ends_at=PostPoll.ends_at - timedelta(days=2)))
        await db.commit()
    assert (await carol.post(f"{A}/posts/{p['id']}/vote", {"option": 0})).json()["error"]["code"] == "poll_closed"
    closed = (await carol.get(f"{A}/posts/{p['id']}")).json()["post"]["poll"]
    assert closed["closed"] and closed["total"] == 1 and closed["options"][2]["votes"] == 1


async def test_poll_validation(client, make_user):
    alice = await make_user("alice")
    for bad in (["only one"], ["a", "b", "c", "d", "e"], ["same", "Same"], ["x" * 41, "y"], ["ok", "  "]):
        r = await alice.post(f"{A}/posts", {"text": "Q?", "poll": bad})
        assert r.status_code == 422, bad
    r = await alice.post(f"{A}/posts", {"poll": ["a", "b"]})
    assert r.status_code == 422  # a poll needs a question


async def test_poll_to_debate_is_an_open_challenge_from_any_post(client, make_user):
    alice = await make_user("alice")
    p = await post(alice, "Tea or coffee for coders?", poll=["Tea", "Coffee"])
    s = (await alice.post(f"{A}/posts/{p['id']}/challenge-question", params={"mode": "open"})).json()
    assert s["question"]
    r = await alice.post(f"{A}/debates", {"question": s["question"], "timing": "async", "source_post_id": p["id"],
                                          "for": {"type": "me"}, "against": {"type": "open"}})
    assert r.status_code == 201, r.text
    assert (await client.get(f"{A}/posts/{p['id']}")).json()["post"]["debates"] == 1


# ── Daily Debate ───────────────────────────────────────────────────────────


async def test_daily_debate_is_created_once_by_the_official_account(client, make_user):
    from backend.app.services.daily import create_daily
    assert (await client.get(f"{A}/daily")).json() == {"daily": None}
    first = await create_daily()
    assert first is not None and await create_daily() is None  # idempotent per day
    d = (await client.get(f"{A}/daily")).json()["daily"]
    assert d["question"] == first.question
    assert d["post"]["author"]["username"] == "provok" and d["post"]["author"]["verified"] is True
    assert [o["label"] for o in d["post"]["poll"]["options"]] == ["Yes", "No"]
    assert d["debate"] is not None and d["post"]["debates"] == 1
    async with SessionFactory() as db:
        assert (await db.scalar(select(User.is_official).where(User.username == "provok"))) is True


# ── Explore, suggestions, new posts ────────────────────────────────────────


async def test_explore_and_who_to_follow(client, make_user):
    alice, bob, carol = await make_user("alice"), await make_user("bob"), await make_user("carol")
    await alice.post(f"{A}/users/bob/follow")
    await bob.post(f"{A}/users/carol/follow")
    await post(carol, "hello #explore")
    sugg = (await alice.get(f"{A}/suggestions/people")).json()["items"]
    assert sugg[0]["user"]["username"] == "carol" and "you follow" in sugg[0]["reason"]
    assert all(s["user"]["username"] not in ("alice", "bob") for s in sugg)
    ex = (await client.get(f"{A}/explore")).json()
    assert {"trends", "top_posts", "people", "live_debates"} <= ex.keys() and ex["top_posts"]


async def test_new_posts_count_for_the_following_banner(client, make_user):
    alice, bob = await make_user("alice"), await make_user("bob")
    await alice.post(f"{A}/users/bob/follow")
    first = await post(bob, "one")
    await post(bob, "two")
    await post(bob, "three")
    r = await alice.get(f"{A}/feed/new", params={"since": first["created_at"]})
    assert r.json() == {"count": 2}


# ── Direct messages ────────────────────────────────────────────────────────


async def test_direct_messages_requests_and_unread(client, make_user):
    alice, bob = await make_user("alice"), await make_user("bob")
    c = (await alice.post(f"{A}/conversations/with/bob")).json()
    again = (await bob.post(f"{A}/conversations/with/alice")).json()
    assert c["id"] == again["id"]  # one conversation per pair, either way round
    r = await alice.post(f"{A}/conversations/{c['id']}/messages", {"text": "  Hi Bob!  "})
    assert r.status_code == 201 and r.json()["text"] == "Hi Bob!" and r.json()["mine"]

    inbox = (await bob.get(f"{A}/conversations")).json()["items"]
    assert inbox[0]["request"] is True and inbox[0]["unread"] is True and inbox[0]["last"]["text"] == "Hi Bob!"
    assert (await bob.get(f"{A}/conversations/unread")).json() == {"unread": 0}  # requests don't light the badge
    await bob.post(f"{A}/conversations/{c['id']}/messages", {"text": "Hey!"})
    assert (await bob.get(f"{A}/conversations")).json()["items"][0]["request"] is False
    assert (await alice.get(f"{A}/conversations/unread")).json() == {"unread": 1}
    thread = (await alice.get(f"{A}/conversations/{c['id']}")).json()
    assert [m["text"] for m in thread["items"]] == ["Hey!", "Hi Bob!"] and thread["with"]["username"] == "bob"
    assert (await alice.get(f"{A}/conversations/unread")).json() == {"unread": 0}  # opening it marks it read

    carol = await make_user("carol")
    assert (await carol.get(f"{A}/conversations/{c['id']}")).status_code == 404  # not a member
    await bob.post(f"{A}/users/alice/block")
    r = await alice.post(f"{A}/conversations/{c['id']}/messages", {"text": "still there?"})
    assert r.status_code == 403
    assert (await carol.post(f"{A}/conversations/with/carol")).status_code == 422


async def test_deleting_an_account_removes_its_conversations(client, make_user):
    alice, bob = await make_user("alice"), await make_user("bob")
    c = (await alice.post(f"{A}/conversations/with/bob")).json()
    await alice.post(f"{A}/conversations/{c['id']}/messages", {"text": "secret"})
    assert [m["text"] for m in (await alice.get(f"{A}/me/export")).json()["messages_sent"]] == ["secret"]
    await alice.post(f"{A}/me/delete", {"password": "correct-horse-battery", "confirm": "DELETE"})
    assert (await bob.get(f"{A}/conversations")).json()["items"] == []
    async with SessionFactory() as db:
        assert await db.scalar(select(Post.id).where(Post.author_id == uuid.UUID(alice.id))) is None
