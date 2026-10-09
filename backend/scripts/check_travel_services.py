"""Probe configured travel providers without printing credentials or response bodies."""

import asyncio

from app.api.v1.travel import connectivity


async def main():
    result = await connectivity(None)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
