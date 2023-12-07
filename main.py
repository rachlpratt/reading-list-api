from google.cloud import datastore
from flask import Flask, request, make_response
import json
import constants

app = Flask(__name__)
client = datastore.Client()


def error(err_string, err_code):
    return json.dumps({"Error": err_string}), err_code


def is_missing_attributes(content, required_attributes):
    for attribute in required_attributes:
        if attribute not in content:
            return True
    return False


def get_paginated_entities(entity_type, limit, offset):
    query = client.query(kind=getattr(constants, entity_type))
    iterator = query.fetch(limit=limit, offset=offset)
    pages = iterator.pages
    results = list(next(pages))
    next_url = None
    if iterator.next_page_token:
        next_offset = offset + limit
        next_url = f"{request.base_url}?limit={limit}&offset={next_offset}"
    for e in results:
        e["id"] = e.key.id
    return results, next_url


def get_self_url(entity):
    return f"{request.url_root}{entity.key.kind}/{entity.key.id}"


def update_entity(entity, content, partial=False):
    if partial:
        for key, value in content.items():
            if key in entity:
                entity[key] = value
    else:
        entity.update(content)
    client.put(entity)
    if "id" not in entity:
        entity["id"] = entity.key.id
        client.put(entity)
    return entity


def get_entity_by_id(entity_type, id):
    entity_key = client.key(getattr(constants, entity_type), int(id))
    entity = client.get(key=entity_key)
    if not entity:
        return None, f"No {entity_type[:-1]} " \
                     f"with this {entity_type[:-1]}_id exists"
    entity["id"] = entity.key.id
    return entity, None


@app.route('/')
def index():
    return "Please navigate to /books or /reading_lists to use this API"


@app.route('/books', methods=['POST', 'GET'])
def books_get_post():
    if 'application/json' not in request.accept_mimetypes:
        return error("The server only sends JSON", 406)
    if request.method == 'POST':
        if request.content_type != 'application/json':
            return error("The server only accepts JSON", 415)
        content = request.get_json()
        new_book = datastore.entity.Entity(key=client.key(constants.BOOKS))
        if is_missing_attributes(content, ["title", "author", "genre"]):
            return error("The request object is missing at least one of "
                         "the required attributes", 400)
        new_book = update_entity(new_book, {"title": content["title"],
                                            "author": content["author"],
                                            "genre": content["genre"]})
        new_book["self"] = get_self_url(new_book)
        return json.dumps(new_book), 201, {'Content-Type': 'application/json'}
    elif request.method == 'GET':
        q_limit = int(request.args.get('limit', '3'))
        q_offset = int(request.args.get('offset', '0'))
        results, next_url = get_paginated_entities("BOOKS", q_limit, q_offset)
        for book in results:
            book["self"] = get_self_url(book)
        output = {"books": results}
        if next_url:
            output["next"] = next_url
        return json.dumps(output)
    elif request.method == 'PUT' or request.method == 'DELETE':
        return error("Method not supported for this route", 405)
    else:
        return 'Method not recognized', 400


@app.route('/books/<id>', methods=['GET', 'DELETE', 'PATCH', 'PUT'])
def books_get_delete_patch_put(id):
    book, error_msg = get_entity_by_id("BOOKS", int(id))
    if error_msg:
        return error(error_msg, 404)
    elif request.method == 'GET':
        book["self"] = get_self_url(book)
        return json.dumps(book)
    if request.method == 'DELETE':
        client.delete(book)
        return '', 204
    elif request.method == 'PATCH' or request.method == 'PUT':
        if 'application/json' not in request.accept_mimetypes:
            return error("The server only sends JSON", 406)
        if request.content_type != 'application/json':
            return error("The server only accepts JSON", 415)
        content = request.get_json()
        if not content:
            return error("No attributes provided", 400)
        partial_update = True if request.method == 'PATCH' else False
        updated_book = update_entity(book, content, partial=partial_update)
        updated_book["self"] = get_self_url(updated_book)
        required_attributes = ["title", "author", "genre"]
        if request.method == 'PUT' and is_missing_attributes(
                content, required_attributes):
            return error("Missing one or more attributes", 400)
        return json.dumps(updated_book), 200, \
               {'Content-Type': 'application/json'}
    else:
        return 'Method not recognized'


@app.route('/reading_lists', methods=['POST', 'GET'])
def reading_lists_post_get():
    if 'application/json' not in request.accept_mimetypes:
        return error("The server only sends JSON", 406)
    if request.method == 'POST':
        if request.content_type != 'application/json':
            return error("The server only accepts JSON", 415)
        content = request.get_json()
        new_book = datastore.entity.Entity(key=client.key(
            constants.READING_LISTS))
        if is_missing_attributes(content, ["name", "description"]):
            return error("The request object is missing at least one of "
                         "the required attributes", 400)
        new_reading_list = update_entity(new_book,
                                         {"name": content["name"],
                                          "description": content["description"],
                                          "books": []})
        new_reading_list["self"] = get_self_url(new_reading_list)
        return json.dumps(new_reading_list), 201, \
               {'Content-Type': 'application/json'}
    elif request.method == 'GET':
        q_limit = int(request.args.get('limit', '3'))
        q_offset = int(request.args.get('offset', '0'))
        results, next_url = get_paginated_entities("READING_LISTS",
                                                   q_limit, q_offset)
        for reading_list in results:
            reading_list["self"] = get_self_url(reading_list)
        output = {"reading_lists": results}
        if next_url:
            output["next"] = next_url
        return json.dumps(output)
    elif request.method == 'PUT' or request.method == 'DELETE':
        return error("Method not supported for this route", 405)
    else:
        return 'Method not recognized', 400


@app.route('/reading_lists/<id>', methods=['GET', 'DELETE', 'PATCH', 'PUT'])
def reading_lists_get_delete_patch_put(id):
    reading_list, error_msg = get_entity_by_id("READING_LISTS", int(id))
    if error_msg:
        return error(error_msg, 404)
    elif request.method == 'GET':
        reading_list["self"] = get_self_url(reading_list)
        return json.dumps(reading_list)
    elif request.method == 'DELETE':
        client.delete(reading_list)
        return '', 204
    elif request.method == 'PATCH' or request.method == 'PUT':
        if 'application/json' not in request.accept_mimetypes:
            return error("The server only sends JSON", 406)
        if request.content_type != 'application/json':
            return error("The server only accepts JSON", 415)
        content = request.get_json()
        if not content:
            return error("No attributes provided", 400)
        partial_update = True if request.method == 'PATCH' else False
        updated_reading_list = update_entity(reading_list, content,
                                             partial=partial_update)
        updated_reading_list["self"] = get_self_url(updated_reading_list)
        required_attributes = ["name", "description"]
        if request.method == 'PUT' and is_missing_attributes(
                content, required_attributes):
            return error("Missing one or more attributes", 400)
        return json.dumps(updated_reading_list), 200, \
               {'Content-Type': 'application/json'}
    else:
        return 'Method not recognized'


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080, debug=True)
