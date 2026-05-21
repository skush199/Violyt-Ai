import asyncio

from app.workers.runner import run_worker_loop


if __name__ == "__main__":
    asyncio.run(run_worker_loop())

