"""AI on posts: Challenge (post → debate), fact-checks, translations, language detection."""
from __future__ import annotations

import pytest

from backend.app.llm.gateway import Role
from backend.app.services import search
from backend.app.services.post_ai import detect_lang
from backend.app.services.search import SearchResult

A = "/api/v1"


@pytest.mark.parametrize(("text", "lang"), [
    ("Chai beats coffee", "en"), ("चाय कॉफ़ी से बेहतर है", "hi"), ("Yaar chai is life", "en"),
    ("চা কফির চেয়ে ভালো", "bn"), ("தேநீர் சிறந்தது", "ta"), ("🙂 123", None), ("", None),
])
def test_detect_lang(text, lang):
    assert detect_lang(text) == lang


async def post(actor, text):
    r = await actor.post(f"{A}/posts", {"text": text})
    assert r.status_code == 201, r.text
    return r.json()


async def test_posts_record_their_language(client, make_user):
    alice = await make_user("alice")
    assert (await post(alice, "चाय सबसे अच्छी है"))["lang"] == "hi"
    assert (await post(alice, "Chai is the best"))["lang"] == "en"


async def test_challenge_turns_a_post_into_a_debate_with_its_author(client, make_user, fake_llm):
    alice, bob = await make_user("alice"), await make_user("bob")
    p = await post(alice, "Remote work kills mentoring. Offices are better for juniors.")
    fake_llm.overrides[Role.POST_QUESTION] = {"question": "Should junior engineers work from the office?",
                                              "author_side": "for", "debatable": True}
    s = (await bob.post(f"{A}/posts/{p['id']}/challenge-question")).json()
    assert s == {"question": "Should junior engineers work from the office?", "author_side": "for",
                 "challenger_side": "against", "author": "alice"}
    assert (await alice.post(f"{A}/posts/{p['id']}/challenge-question")).json()["error"]["code"] == "self_challenge"

    r = await bob.post(f"{A}/debates", {"question": s["question"], "timing": "async", "source_post_id": p["id"],
                                        "for": {"type": "invite", "username": "alice"}, "against": {"type": "me"}})
    assert r.status_code == 201, r.text
    view = (await client.get(f"{A}/posts/{p['id']}")).json()["post"]
    assert view["debates"] == 1
    cards = (await client.get(f"{A}/posts/{p['id']}/debates")).json()["items"]
    assert [c["id"] for c in cards] == [r.json()["id"]]
    assert view["author"]["debates"] == 0  # credibility: finished debates count


async def test_cannot_challenge_across_a_block(client, make_user):
    alice, bob = await make_user("alice"), await make_user("bob")
    await alice.post(f"{A}/users/bob/block")
    r = await bob.post(f"{A}/debates", {"question": "Is tea better than coffee for mornings?", "timing": "async",
                                        "for": {"type": "me"}, "against": {"type": "invite", "username": "alice"}})
    assert r.status_code == 403 and r.json()["error"]["code"] == "blocked"


async def test_not_debatable_posts_are_refused(client, make_user, fake_llm):
    alice, bob = await make_user("alice"), await make_user("bob")
    p = await post(alice, "Good morning everyone!")
    fake_llm.overrides[Role.POST_QUESTION] = {"question": None, "author_side": "for", "debatable": False}
    r = await bob.post(f"{A}/posts/{p['id']}/challenge-question")
    assert r.status_code == 422 and r.json()["error"]["code"] == "not_debatable"


class FakeSearch:
    def __init__(self, results):
        self.results, self.calls = results, 0

    async def search(self, query, max_results):
        self.calls += 1
        return self.results


async def test_factcheck_runs_once_and_is_shared(client, make_user, jobs, fake_llm):
    alice, bob, carol = await make_user("alice"), await make_user("bob"), await make_user("carol")
    p = await post(alice, "India won the 2011 Cricket World Cup.")
    fake = FakeSearch([SearchResult("2011 Cricket World Cup final", "https://example.com/wc2011", "India beat Sri Lanka."),
                       SearchResult("Other", "https://example.com/other", "Unrelated.")])
    search.set_search_provider(fake)
    try:
        r = await bob.post(f"{A}/posts/{p['id']}/factcheck")
        assert r.json()["status"] == "pending"
        await jobs.run()
        done = (await client.get(f"{A}/posts/{p['id']}/factcheck")).json()
        assert done["status"] == "done" and done["rating"] == "mostly_accurate"
        assert done["sources"] == [{"title": "2011 Cricket World Cup final", "url": "https://example.com/wc2011"}]
        # A second reader gets the same result; nothing runs again.
        again = (await carol.post(f"{A}/posts/{p['id']}/factcheck")).json()
        assert again["status"] == "done" and not jobs.jobs and fake.calls == 1
        assert (await client.get(f"{A}/posts/{p['id']}")).json()["post"]["factcheck"]["rating"] == "mostly_accurate"
    finally:
        search.set_search_provider(None)


async def test_factcheck_without_sources_fails_and_opinions_are_marked(client, make_user, jobs, fake_llm):
    alice, bob = await make_user("alice"), await make_user("bob")
    search.set_search_provider(FakeSearch([]))
    try:
        p = await post(alice, "The moon is 384,400 km away.")
        await bob.post(f"{A}/posts/{p['id']}/factcheck")
        await jobs.run()
        assert (await client.get(f"{A}/posts/{p['id']}/factcheck")).json()["status"] == "failed"

        search.set_search_provider(FakeSearch([SearchResult("t", "https://example.com", "c")]))
        fake_llm.overrides[Role.FACT_CHECK] = {"checkable": False}
        o = await post(alice, "Biryani is the best food.")
        await bob.post(f"{A}/posts/{o['id']}/factcheck")
        await jobs.run()
        assert (await client.get(f"{A}/posts/{o['id']}/factcheck")).json()["status"] == "opinion"
    finally:
        search.set_search_provider(None)


async def test_translation_is_cached(client, make_user, fake_llm):
    alice, bob = await make_user("alice"), await make_user("bob")
    p = await post(alice, "Chai is life")
    first = (await bob.post(f"{A}/posts/{p['id']}/translate", params={"to": "hi"})).json()
    calls = sum(1 for role, _ in fake_llm.calls if role is Role.TRANSLATE)
    second = (await alice.post(f"{A}/posts/{p['id']}/translate", params={"to": "hi"})).json()
    assert first == second == {"lang": "hi", "text": "अनुवादित पाठ"}
    assert sum(1 for role, _ in fake_llm.calls if role is Role.TRANSLATE) == calls == 1
    r = await bob.post(f"{A}/posts/{p['id']}/translate", params={"to": "fr"})
    assert r.status_code == 422
