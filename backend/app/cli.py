"""
Operational CLI.

    python -m backend.app.cli migrate
    python -m backend.app.cli create-admin --email you@x.com --username you --password '...'
    python -m backend.app.cli promote --username someone
    python -m backend.app.cli seed-models
    python -m backend.app.cli seed-featured --count 3
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import func, select

from backend.app.core.config import BACKEND_DIR
from backend.app.core.logging import setup_logging
from backend.app.core.security import password_problem, utcnow
from backend.app.db.session import session_scope


def migrate() -> int:
    from alembic import command
    from alembic.config import Config
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")
    return 0


async def create_admin(email: str, username: str, password: str) -> None:
    from backend.app.services.auth import create_user, get_user_by_email, username_problem
    if problem := username_problem(username) or password_problem(password, email=email, username=username):
        raise SystemExit(problem)
    async with session_scope() as db:
        user = await get_user_by_email(db, email)
        if user is None:
            user = await create_user(db, email=email, username=username, display_name=username, password=password,
                                     verified=True)
        user.role = "admin"
        user.email_verified_at = user.email_verified_at or utcnow()
    print(f"admin ready: {email}")


async def promote(username: str) -> None:
    from backend.app.models import User
    async with session_scope() as db:
        user = await db.scalar(select(User).where(func.lower(User.username) == username.lower()))
        if user is None:
            raise SystemExit("no such user")
        user.role = "admin"
    print(f"promoted {username}")


async def seed_models() -> None:
    from backend.app.llm.registry import seed_registry
    async with session_scope() as db:
        print(f"seeded {await seed_registry(db)} models")


async def seed_featured(count: int) -> None:
    from backend.app.services.featured import create_featured
    from backend.app.workers.queue import close_pool
    ids = await create_featured(count)
    await close_pool()
    print("created:", ", ".join(ids) or "none (no enabled models or AI debates paused)")


def main() -> None:
    setup_logging()
    p = argparse.ArgumentParser(prog="provok")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    a = sub.add_parser("create-admin")
    a.add_argument("--email", required=True)
    a.add_argument("--username", required=True)
    a.add_argument("--password", required=True)
    pr = sub.add_parser("promote")
    pr.add_argument("--username", required=True)
    sub.add_parser("seed-models")
    f = sub.add_parser("seed-featured")
    f.add_argument("--count", type=int, default=1)
    args = p.parse_args()
    if args.cmd == "migrate":
        raise SystemExit(migrate())
    coro = {
        "create-admin": lambda: create_admin(args.email, args.username.lower(), args.password),
        "promote": lambda: promote(args.username),
        "seed-models": seed_models,
        "seed-featured": lambda: seed_featured(args.count),
    }[args.cmd]()
    asyncio.run(coro)


if __name__ == "__main__":
    main()
