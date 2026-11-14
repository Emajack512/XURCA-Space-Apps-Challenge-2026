"""Desktop entry point and configuration commands exposed to Svelte."""

from anyio import to_thread
from anyio.from_thread import start_blocking_portal
from pytauri import Commands, builder_factory, context_factory
from pytauri.ipc import InvokeException
from pydantic import BaseModel

import json

from .services.acquisition import acquire
from .services.public_sources import find_places

from .configuration import (
    ConfigurationName,
    ConfigurationSnapshot,
    read_configuration,
    write_configurations,
)

commands: Commands = Commands()


@commands.command()
async def load_configuration(body: ConfigurationName) -> str:
    return await to_thread.run_sync(read_configuration, body.name)


@commands.command()
async def save_configuration(body: ConfigurationSnapshot) -> bool:
    await to_thread.run_sync(write_configurations, body)
    return True


class AcquisitionRequest(BaseModel):
    investigation: dict


@commands.command()
async def acquire_data(body: AcquisitionRequest) -> str:
    try:
        series = await to_thread.run_sync(acquire, body.investigation)
    except ValueError as error:
        raise InvokeException(str(error)) from error
    return json.dumps(series, allow_nan=False)


class PlaceRequest(BaseModel):
    query: str
    kind: str
    language: str = "es"


@commands.command()
async def search_places(body: PlaceRequest) -> str:
    try:
        places = await to_thread.run_sync(find_places, body.query, body.kind, body.language)
    except ValueError as error:
        raise InvokeException(str(error)) from error
    return json.dumps(places, allow_nan=False)


def main() -> int:
    with start_blocking_portal("asyncio") as portal:
        app = builder_factory().build(
            context=context_factory(),
            invoke_handler=commands.generate_handler(portal),
        )
        return app.run_return()
