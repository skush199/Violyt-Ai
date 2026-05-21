import asyncio

from app.db.session import AsyncSessionLocal
from app.services.bootstrap import seed_rbac


async def main() -> None:
    async with AsyncSessionLocal() as session:
        await seed_rbac(session)


if __name__ == "__main__":
    asyncio.run(main())

