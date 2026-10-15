"""terrella-catalog serve | create-user | openapi"""
import argparse
import json
import sys

from sqlalchemy import select

from .auth import hash_token, new_token
from .config import Settings
from .db import Database
from .models import ROLES, User
from .schemas import nanos


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="terrella-catalog")
    sub = p.add_subparsers(dest="cmd", required=True)
    sv = sub.add_parser("serve")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8080)
    cu = sub.add_parser("create-user", help="Bootstrap a user (e.g. the first admin) and print its token")
    cu.add_argument("name")
    cu.add_argument("--role", choices=ROLES, default="user")
    cu.add_argument("--budget-usd", type=float, default=None)
    oa = sub.add_parser("openapi", help="Print the OpenAPI schema")
    oa.add_argument("--out", default="-")
    args = p.parse_args(argv)

    if args.cmd == "serve":
        import uvicorn

        from .app import create_app

        uvicorn.run(create_app(), host=args.host, port=args.port)
    elif args.cmd == "create-user":
        db = Database(Settings.from_env().database_url)
        with db.sessionmaker() as s:
            if s.scalar(select(User).where(User.name == args.name)):
                sys.exit(f"user {args.name} exists")
            token = new_token()
            u = User(name=args.name, role=args.role, token_hash=hash_token(token), monthly_budget_nanos=nanos(args.budget_usd))
            s.add(u)
            s.commit()
            print(json.dumps({"id": u.id, "name": u.name, "role": u.role, "token": token}))
    elif args.cmd == "openapi":
        from .app import create_app
        from .config import Settings as S

        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d:
            app = create_app(S(database_url="sqlite:///:memory:", blob_dir=Path(d), public_base_url=""))
            text = json.dumps(app.openapi(), indent=2)
        if args.out == "-":
            print(text)
        else:
            Path(args.out).write_text(text + "\n")


if __name__ == "__main__":
    main()
