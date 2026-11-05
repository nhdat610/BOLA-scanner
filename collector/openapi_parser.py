import json
import yaml
from pathlib import Path
from urllib.parse import urlsplit

HTTP_METHODS = {
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "head",
    "options"
}


def parse_openapi_text(content):
    try:
        document = json.loads(content)
    except json.JSONDecodeError:
        document = yaml.safe_load(content)

    return parse_openapi_document(document)


def parse_openapi_file(file_path):
    content = Path(file_path).read_text(encoding="utf-8")

    return parse_openapi_text(content)


def parse_openapi_document(document):
    if not isinstance(document, dict):
        raise ValueError("Invalid OpenAPI document")

    if not document.get("openapi") and not document.get("swagger"):
        raise ValueError("OpenAPI/Swagger version not found")

    endpoints = []

    for path, path_item in document.get("paths", {}).items():

        if not isinstance(path_item, dict):
            continue

        path_parameters = path_item.get("parameters", [])

        for method, operation in path_item.items():

            if method.lower() not in HTTP_METHODS:
                continue

            if not isinstance(operation, dict):
                continue

            parameters = []

            all_parameters = (
                path_parameters
                + operation.get("parameters", [])
            )

            for parameter in all_parameters:
                parameters.append({
                    "name": parameter.get("name"),
                    "in": parameter.get("in"),
                    "required": parameter.get("required", False),
                    "schema": parameter.get("schema")
                })

            request_body = None

            # OpenAPI 3.x
            body_info = operation.get("requestBody")

            if body_info:
                content = body_info.get("content", {})

                json_content = content.get(
                    "application/json", {}
                )

                request_body = json_content.get("schema")

            # Swagger 2.0
            if document.get("swagger"):
                for parameter in all_parameters:
                    if parameter.get("in") == "body":
                        request_body = parameter.get("schema")

            endpoints.append({
                "method": method.upper(),
                "path": path,
                "operation_id": operation.get("operationId"),
                "parameters": parameters,
                "request_body": request_body,
                "responses": list(
                    operation.get("responses", {}).keys()
                )
            })

    info = document.get("info", {})

    return {
        "version": document.get("openapi") or document.get("swagger"),
        "title": info.get("title"),
        "endpoints": endpoints
    }


async def fetch_openapi(context, url, allowed_hosts):
    host = urlsplit(url).hostname

    if not host or host.lower() not in {
        item.lower() for item in allowed_hosts
    }:
        raise ValueError("OpenAPI URL is outside the allowed scope")

    # GET only: retrieve the specification.
    response = await context.request.get(
        url,
        timeout=15000
    )

    if not response.ok:
        raise RuntimeError(
            f"Cannot retrieve OpenAPI: HTTP {response.status}"
        )

    content = await response.text()

    return parse_openapi_text(content)
