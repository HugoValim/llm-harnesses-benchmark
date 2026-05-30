from collections.abc import Mapping
from typing import cast

from asgiref.sync import sync_to_async
from django.template.loader import render_to_string


async def render_html(template_name: str, context: Mapping[str, object]) -> str:
    html = await sync_to_async(render_to_string, thread_sensitive=True)(
        template_name,
        dict(context),
    )
    return cast(str, html)
