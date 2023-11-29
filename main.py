from google.cloud import datastore
from flask import Flask, request
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


def update_entity(entity, content):
    entity.update(content)
    client.put(entity)
    entity["id"] = entity.key.id
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
    if request.method == 'POST':
        content = request.get_json()
        new_book = datastore.entity.Entity(key=client.key(constants.BOOKS))
        if is_missing_attributes(content, ["title", "author", "genre"]):
            return error("The request object is missing at least one of "
                         "the required attributes", 400)
        new_book = update_entity(new_book, {"title": content["title"],
                                            "author": content["author"],
                                            "genre": content["genre"]})
        new_book["self"] = get_self_url(new_book)
        return json.dumps(new_book), 201
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
    else:
        return 'Method not recognized', 400


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080, debug=True)
