import json
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import yaml


HTTP_METHODS = {
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "head",
    "options"
}


def is_json_content_type(content_type):
    content_type = content_type.lower()

    return (
        "application/json" in content_type
        or content_type.endswith("+json")
    )


def parse_openapi_text(content):
    try:
        document = yaml.safe_load(content)

    except yaml.YAMLError as error:
        raise ValueError(
            "Cannot read OpenAPI specification"
        ) from error

    return parse_openapi_document(document)


def parse_openapi_file(file_path):
    content = Path(file_path).read_text(
        encoding="utf-8"
    )

    return parse_openapi_text(content)


def parse_openapi_document(document):
    if not isinstance(document, dict):
        raise ValueError("Invalid OpenAPI document")

    version = (
        document.get("openapi")
        or document.get("swagger")
    )

    if not version:
        raise ValueError(
            "OpenAPI/Swagger version not found"
        )

    paths = document.get("paths", {})

    if not isinstance(paths, dict):
        raise ValueError("Invalid OpenAPI paths")

    endpoints = []

    for path, path_item in paths.items():

        if not isinstance(path_item, dict):
            continue

        path_parameters = path_item.get("parameters") or []

        if not isinstance(path_parameters, list):
            path_parameters = []

        for method, operation in path_item.items():

            if method.lower() not in HTTP_METHODS:
                continue

            if not isinstance(operation, dict):
                continue

            operation_parameters = (
                operation.get("parameters") or []
            )

            if not isinstance(operation_parameters, list):
                operation_parameters = []

            all_parameters = (
                path_parameters + operation_parameters
            )

            parameters = []

            for parameter in all_parameters:

                if not isinstance(parameter, dict):
                    continue

                parameters.append({
                    "name": parameter.get("name"),
                    "in": parameter.get("in"),
                    "required": parameter.get(
                        "required", False
                    ),
                    "schema": parameter.get("schema"),
                    "ref": parameter.get("$ref")
                })

            request_body = None

            # OpenAPI 3.x
            body_info = operation.get("requestBody")

            if isinstance(body_info, dict):
                content = body_info.get("content") or {}

                if isinstance(content, dict):
                    for content_type, media_info in content.items():

                        if not is_json_content_type(
                            content_type
                        ):
                            continue

                        if isinstance(media_info, dict):
                            request_body = media_info.get(
                                "schema"
                            )

                        break

                # Preserve a reference if requestBody uses $ref.
                if "$ref" in body_info:
                    request_body = {
                        "$ref": body_info["$ref"]
                    }

            # Swagger 2.0
            if document.get("swagger"):
                for parameter in all_parameters:

                    if (
                        isinstance(parameter, dict)
                        and parameter.get("in") == "body"
                    ):
                        request_body = parameter.get("schema")

            responses = operation.get("responses") or {}

            if not isinstance(responses, dict):
                responses = {}

            endpoints.append({
                "method": method.upper(),
                "path": path,
                "operation_id": operation.get(
                    "operationId"
                ),
                "parameters": parameters,
                "request_body": request_body,
                "responses": list(responses.keys())
            })

    info = document.get("info") or {}

    if not isinstance(info, dict):
        info = {}

    return {
        "version": version,
        "title": info.get("title"),
        "endpoints": endpoints
    }


async def fetch_openapi(url, allowed_hosts):
    parts = urlsplit(url)

    if parts.scheme.lower() not in ("http", "https"):
        raise ValueError("Invalid OpenAPI URL")

    if not parts.hostname:
        raise ValueError("Invalid OpenAPI URL")

    allowed_hosts = {
        host.lower() for host in allowed_hosts
    }

    if parts.hostname.lower() not in allowed_hosts:
        raise ValueError(
            "OpenAPI URL is outside the allowed scope"
        )

    # GET only: retrieve the OpenAPI specification.
    async with httpx.AsyncClient(
        timeout=15,
        follow_redirects=False
    ) as client:

        response = await client.get(url)
        response.raise_for_status()

        return parse_openapi_text(response.text)