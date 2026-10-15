"""The social layer through the HTTP API: posts, threads, reactions, feeds, blocks, mutes, moderation, media."""
from __future__ import annotations

import io
import uuid
from datetime import timedelta

from sqlalchemy import select, update

from backend.app.db.session import SessionFactory
from backend.app.llm.gateway import Role
from backend.app.models import Post

A = "/api/v1"


async def post(actor, text="Hello arena", **extra):
    r = await actor.post(f"{A}/posts", {"text": text, **extra})
    assert r.status_code == 201, r.text
    return r.json()


async def notifications(actor) -> list[dict]:
    return (await actor.get(f"{A}/notifications")).json()["items"]


async def test_create_post_with_hashtags_and_mentions(client, make_user, jobs):
    alice, bob = await make_user("alice"), await make_user("bob")
    p = await post(alice, "Cricket beats football. @bob agree? #Cricket #IPL2027 #1 #क्रिकेट")
    assert p["author"]["username"] == "alice" and p["counts"] == {"replies": 0, "reposts": 0, "quotes": 0, "likes": 0, "views": 0}
    assert p["viewer"]["is_author"] is True and p["reposted_by"] is None
    tags = (await client.get(f"{A}/tags/cricket")).json()
    assert [i["id"] for i in tags["items"]] == [p["id"]]
    assert (await client.get(f"{A}/tags/क्रिकेट")).json()["items"][0]["id"] == p["id"]  # Hindi hashtags work
    assert (await client.get(f"{A}/tags/1")).json()["items"] == []  # "#1" is a number, not a topic
    mention = [n for n in await notifications(bob) if n["kind"] == "mention"]
    assert len(mention) == 1 and mention[0]["link"] == f"/p/{p['id']}"
    assert jobs.names() == ["moderate_post"]


async def test_post_validation(client, make_user):
    alice = await make_user("alice")
    r = await alice.post(f"{A}/posts", {"text": "   "})
    assert r.status_code == 422 and r.json()["error"]["code"] == "empty_post"
    r = await alice.post(f"{A}/posts", {"text": "x" * 501})
    assert r.status_code == 422 and r.json()["error"]["code"] == "too_long"
    r = await alice.post(f"{A}/posts", {"text": "Who wins the next Lok Sabha election?"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "blocked_category"
    unverified = await make_user("newbie", verified=False)
    r = await unverified.post(f"{A}/posts", {"text": "hi"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "email_unverified"


async def test_replies_build_a_thread(client, make_user):
    alice, bob, carol = await make_user("alice"), await make_user("bob"), await make_user("carol")
    root = await post(alice, "Is remote work better?")
    r1 = await post(bob, "Yes, no commute.", reply_to_id=root["id"])
    r2 = await post(carol, "But mentoring suffers.", reply_to_id=r1["id"])
    assert r1["reply_to"] == {"id": root["id"], "username": "alice"}

    thread = (await client.get(f"{A}/posts/{r2['id']}")).json()
    assert [a["id"] for a in thread["ancestors"]] == [root["id"], r1["id"]]
    assert thread["post"]["id"] == r2["id"]
    assert (await client.get(f"{A}/posts/{root['id']}")).json()["post"]["counts"]["replies"] == 1
    replies = (await client.get(f"{A}/posts/{root['id']}/replies")).json()["items"]
    assert [x["id"] for x in replies] == [r1["id"]]
    assert any(n["kind"] == "reply" for n in await notifications(alice))

    # Deleting a reply gives the count back; only the author (or an admin) can delete.
    assert (await alice.client.delete(f"{A}/posts/{r1['id']}", headers=alice.h)).status_code == 403
    assert (await bob.client.delete(f"{A}/posts/{r1['id']}", headers=bob.h)).status_code == 200
    assert (await client.get(f"{A}/posts/{root['id']}")).json()["post"]["counts"]["replies"] == 0
    assert (await client.get(f"{A}/posts/{r1['id']}")).status_code == 404


async def test_likes_are_idempotent_and_notify_once(client, make_user):
    alice, bob = await make_user("alice"), await make_user("bob")
    p = await post(alice)
    for _ in range(2):
        r = await bob.post(f"{A}/posts/{p['id']}/like")
        assert r.status_code == 200 and r.json()["counts"]["likes"] == 1 and r.json()["viewer"]["liked"]
    assert len([n for n in await notifications(alice) if n["kind"] == "like"]) == 1
    r = await bob.client.delete(f"{A}/posts/{p['id']}/like", headers=bob.h)
    assert r.json()["counts"]["likes"] == 0 and not r.json()["viewer"]["liked"]
    r = await bob.client.delete(f"{A}/posts/{p['id']}/like", headers=bob.h)
    assert r.json()["counts"]["likes"] == 0
    # Liking your own post doesn't notify you.
    await alice.post(f"{A}/posts/{p['id']}/like")
    assert len([n for n in await notifications(alice) if n["kind"] == "like"]) == 1


async def test_reposts_and_quotes(client, make_user):
    alice, bob, carol = await make_user("alice"), await make_user("bob"), await make_user("carol")
    await carol.post(f"{A}/users/bob/follow")
    p = await post(alice, "Original take")
    for _ in range(2):
        r = await bob.post(f"{A}/posts/{p['id']}/repost")
        assert r.json()["counts"]["reposts"] == 1 and r.json()["viewer"]["reposted"]

    feed = (await carol.get(f"{A}/feed?tab=following")).json()["items"]
    assert len(feed) == 1 and feed[0]["id"] == p["id"] and feed[0]["reposted_by"]["username"] == "bob"
    # Liking the repost likes the original.
    r = await carol.post(f"{A}/posts/{feed[0]['feed_id']}/like")
    assert r.json()["id"] == p["id"] and r.json()["counts"]["likes"] == 1

    q = await post(carol, "Hard disagree", quote_of_id=p["id"])
    assert q["quote"]["id"] == p["id"] and q["quote"]["author"]["username"] == "alice"
    assert (await client.get(f"{A}/posts/{p['id']}")).json()["post"]["counts"]["quotes"] == 1

    r = await bob.client.delete(f"{A}/posts/{p['id']}/repost", headers=bob.h)
    assert r.json()["counts"]["reposts"] == 0
    left = (await carol.get(f"{A}/feed?tab=following")).json()["items"]
    assert [i["id"] for i in left] == [q["id"]]  # only carol's own quote; bob's repost is gone


async def test_following_feed_pages_with_a_cursor(client, make_user):
    alice, bob, carol = await make_user("alice"), await make_user("bob"), await make_user("carol")
    await alice.post(f"{A}/users/bob/follow")
    mine = await post(alice, "my own post")
    bobs = [await post(bob, f"bob {i}") for i in range(30)]
    await post(carol, "not followed")
    await post(bob, "a reply", reply_to_id=mine["id"])  # replies stay out of the home timeline

    first = (await alice.get(f"{A}/feed?tab=following")).json()
    assert len(first["items"]) == 25 and first["next_cursor"]
    second = (await alice.get(f"{A}/feed", params={"tab": "following", "cursor": first["next_cursor"]})).json()
    ids = [i["id"] for i in first["items"] + second["items"]]
    assert ids == [p["id"] for p in reversed(bobs)] + [mine["id"]] and second["next_cursor"] is None
    assert any(n["kind"] == "follow" for n in await notifications(bob))
    assert (await client.get(f"{A}/feed?tab=following")).json()["items"] == []  # signed out


async def test_for_you_ranks_engagement_over_recency(client, make_user):
    alice, bob, carol = await make_user("alice"), await make_user("bob"), await make_user("carol")
    quiet = await post(alice, "quiet post")
    popular = await post(bob, "popular post")
    await post(carol, "a reply", reply_to_id=quiet["id"])
    for fan in [await make_user(f"fan{i}") for i in range(6)]:
        await fan.post(f"{A}/posts/{popular['id']}/like")
    async with SessionFactory() as db:  # make the popular post an hour older than the quiet one
        await db.execute(update(Post).where(Post.id == uuid.UUID(popular["id"]))
                         .values(created_at=Post.created_at - timedelta(hours=1)))
        await db.commit()
    items = (await client.get(f"{A}/feed")).json()["items"]
    ids = [i["id"] for i in items]
    assert ids.index(popular["id"]) < ids.index(quiet["id"])
    assert all(i["reply_to"] is None for i in items)  # no replies in For You


async def test_block_hides_both_ways_and_stops_interaction(client, make_user):
    alice, bob = await make_user("alice"), await make_user("bob")
    await alice.post(f"{A}/users/bob/follow")
    await bob.post(f"{A}/users/alice/follow")
    p = await post(alice, "alice's post")
    await post(bob, "bob's post")

    assert (await alice.post(f"{A}/users/bob/block")).json() == {"blocked": True}
    assert (await bob.get(f"{A}/posts/{p['id']}")).status_code == 404
    assert (await bob.post(f"{A}/posts", {"text": "hey", "reply_to_id": p["id"]})).status_code == 404
    assert (await bob.post(f"{A}/users/alice/follow")).status_code == 403
    assert all(i["author"]["username"] != "alice" for i in (await bob.get(f"{A}/feed")).json()["items"])
    assert all(i["author"]["username"] != "bob" for i in (await alice.get(f"{A}/feed")).json()["items"])
    assert (await bob.get(f"{A}/users/alice/posts")).json()["blocked"] is True
    profile = (await alice.get(f"{A}/users/bob")).json()
    assert profile["is_blocked"] is True and profile["followers"] == 0 and profile["following"] == 0

    await alice.client.delete(f"{A}/users/bob/block", headers=alice.h)
    assert (await bob.get(f"{A}/posts/{p['id']}")).status_code == 200


async def test_mute_hides_posts_and_notifications_silently(client, make_user):
    alice, bob = await make_user("alice"), await make_user("bob")
    p = await post(alice)
    await post(bob, "noise")
    await alice.post(f"{A}/users/bob/mute")
    await bob.post(f"{A}/posts/{p['id']}/like")
    assert not [n for n in await notifications(alice) if n["kind"] == "like"]
    assert all(i["author"]["username"] != "bob" for i in (await alice.get(f"{A}/feed")).json()["items"])
    assert (await bob.get(f"{A}/posts/{p['id']}")).status_code == 200  # bob isn't told and can still see alice


async def test_moderation_hides_a_flagged_post(client, make_user, jobs, fake_llm):
    alice = await make_user("alice")
    fake_llm.overrides[Role.MODERATION] = {"flagged": True, "categories": ["harassment"], "severity": "high",
                                           "reason": "insult"}
    p = await post(alice, "something nasty")
    await jobs.run()
    assert (await client.get(f"{A}/posts/{p['id']}")).status_code == 404
    assert any(n["kind"] == "moderation" for n in await notifications(alice))
    async with SessionFactory() as db:
        assert (await db.scalar(select(Post.moderation_reason).where(Post.id == uuid.UUID(p["id"])))) == "harassment"


async def test_media_upload_and_attach(client, make_user):
    from PIL import Image
    alice, bob = await make_user("alice"), await make_user("bob")
    buf = io.BytesIO()
    Image.new("RGB", (3000, 1500), "orange").save(buf, format="PNG")
    r = await alice.client.post(f"{A}/media", files={"file": ("a.png", buf.getvalue(), "image/png")}, headers=alice.h)
    assert r.status_code == 201, r.text
    m = r.json()
    assert (m["width"], m["height"]) == (2048, 1024) and m["url"].endswith(".webp")
    # Someone else can't attach it; the owner can, once.
    r = await bob.post(f"{A}/posts", {"text": "stolen", "media_ids": [m["id"]]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "bad_media"
    p = await post(alice, "", media_ids=[m["id"]])
    assert p["text"] is None and p["media"][0]["id"] == m["id"]
    r = await alice.post(f"{A}/posts", {"text": "again", "media_ids": [m["id"]]})
    assert r.status_code == 422
    assert (await alice.get(f"{A}/users/alice/posts?tab=media")).json()["items"][0]["id"] == p["id"]
    r = await alice.client.post(f"{A}/media", files={"file": ("x.png", b"not an image", "image/png")}, headers=alice.h)
    assert r.status_code == 415


async def test_bookmarks_trends_search_and_reports(client, make_user):
    alice, bob = await make_user("alice"), await make_user("bob")
    p = await post(alice, "Startups or big tech? #careers")
    await post(bob, "Big tech for me #careers")
    await bob.post(f"{A}/posts/{p['id']}/bookmark")
    saved = (await bob.get(f"{A}/me/bookmarks")).json()["items"]
    assert [x["id"] for x in saved] == [p["id"]] and saved[0]["viewer"]["bookmarked"]

    assert {"tag": "careers", "people": 2, "posts": 2} in (await client.get(f"{A}/trends")).json()["items"]
    await post(alice, "solo #onlyme")
    await post(alice, "again #onlyme")
    assert all(t["tag"] != "onlyme" for t in (await client.get(f"{A}/trends")).json()["items"])

    found = (await client.get(f"{A}/search", params={"q": "big tech"})).json()["posts"]
    assert len(found) == 2
    r = await bob.post(f"{A}/reports", {"target_type": "post", "target_id": p["id"], "reason": "spam"})
    assert r.status_code == 201


async def test_deleting_an_account_deletes_its_posts(client, make_user):
    alice, bob = await make_user("alice"), await make_user("bob")
    p = await post(alice, "goodbye")
    await bob.post(f"{A}/posts/{p['id']}/like")
    export = (await alice.get(f"{A}/me/export")).json()
    assert [x["text"] for x in export["posts"]] == ["goodbye"]
    r = await alice.post(f"{A}/me/delete", {"password": "correct-horse-battery", "confirm": "DELETE"})
    assert r.status_code == 200, r.text
    assert (await client.get(f"{A}/posts/{p['id']}")).status_code == 404


async def test_posting_is_rate_limited(client, make_user, monkeypatch):
    from backend.app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "rl_post_user", "2/3600")
    alice = await make_user("alice")
    await post(alice, "one")
    await post(alice, "two")
    r = await alice.post(f"{A}/posts", {"text": "three"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"
