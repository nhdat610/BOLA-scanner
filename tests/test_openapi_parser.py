from collector.openapi_parser import (
    parse_openapi_document,
    parse_openapi_text
)


def test_parse_openapi_document():
    document = {
        "openapi": "3.0.0",
        "info": {
            "title": "Book API",
            "version": "1.0"
        },
        "paths": {
            "/books/{book_id}": {
                "get": {
                    "operationId": "getBook",
                    "parameters": [
                        {
                            "name": "book_id",
                            "in": "path",
                            "required": True,
                            "schema": {
                                "type": "integer"
                            }
                        }
                    ],
                    "responses": {
                        "200": {},
                        "404": {}
                    }
                }
            }
        }
    }

    result = parse_openapi_document(document)

    assert result["version"] == "3.0.0"
    assert result["title"] == "Book API"
    assert len(result["endpoints"]) == 1

    endpoint = result["endpoints"][0]

    assert endpoint["method"] == "GET"
    assert endpoint["path"] == "/books/{book_id}"
    assert endpoint["operation_id"] == "getBook"


def test_parse_openapi_text():
    content = """
openapi: 3.0.0
info:
  title: Test API
paths:
  /users:
    get:
      responses:
        '200':
          description: Success
"""

    result = parse_openapi_text(content)

    assert result["title"] == "Test API"
    assert len(result["endpoints"]) == 1


def test_reject_invalid_openapi_document():
    document = {
        "info": {
            "title": "Invalid API"
        },
        "paths": {}
    }

    try:
        parse_openapi_document(document)
        assert False, "Expected ValueError"

    except ValueError:
        assert True


def test_parse_json_request_body():
    document = {
        "openapi": "3.0.0",
        "info": {
            "title": "Book API"
        },
        "paths": {
            "/books": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "name": {
                                            "type": "string"
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "responses": {
                        "201": {}
                    }
                }
            }
        }
    }

    result = parse_openapi_document(document)

    endpoint = result["endpoints"][0]

    assert endpoint["method"] == "POST"
    assert endpoint["request_body"]["type"] == "object"