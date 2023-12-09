import json
from six.moves.urllib.request import urlopen

from flask import Flask, request, redirect, \
    render_template, session, url_for
from google.cloud import datastore
from jose import jwt
import constants
from constants import CLIENT_ID, CLIENT_SECRET, ALGORITHMS, DOMAIN
from authlib.integrations.flask_client import OAuth
import base64

app = Flask(__name__)
app.secret_key = "APP_SECRET_KEY"

client = datastore.Client()

oauth = OAuth(app)

auth0 = oauth.register(
    'auth0',
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    api_base_url="https://" + DOMAIN,
    access_token_url="https://" + DOMAIN + "/oauth/token",
    authorize_url="https://" + DOMAIN + "/authorize",
    client_kwargs={
        'scope': 'openid profile email',
    },
    server_metadata_url=f'https://{DOMAIN}'
                        f'/.well-known/openid-configuration'
)

# This code is adapted from https://auth0.com/docs/quickstart/backend/
# python/01-authorization?_ga=2.46956069.349333901.1589042886-466012638.
# 1589042885#create-the-jwt-validation-decorator


class AuthError(Exception):
    def __init__(self, error, status_code):
        self.error = error
        self.status_code = status_code


# Verify the JWT in the request's Authorization header
def verify_jwt(request):
    if 'Authorization' in request.headers:
        auth_header = request.headers['Authorization'].split()
        token = auth_header[1]
    else:
        raise AuthError({"code": "no auth header",
                         "description":
                             "Authorization header is missing"}, 401)

    jsonurl = urlopen("https://" + DOMAIN + "/.well-known/jwks.json")
    jwks = json.loads(jsonurl.read())
    try:
        unverified_header = jwt.get_unverified_header(token)
    except jwt.JWTError:
        raise AuthError({"code": "invalid_header",
                         "description":
                             "Invalid header. "
                             "Use an RS256 signed JWT Access Token"}, 401)
    if unverified_header["alg"] == "HS256":
        raise AuthError({"code": "invalid_header",
                         "description":
                             "Invalid header. "
                             "Use an RS256 signed JWT Access Token"}, 401)
    rsa_key = {}
    for key in jwks["keys"]:
        if key["kid"] == unverified_header["kid"]:
            rsa_key = {
                "kty": key["kty"],
                "kid": key["kid"],
                "use": key["use"],
                "n": key["n"],
                "e": key["e"]
            }
    if rsa_key:
        try:
            payload = jwt.decode(
                token,
                rsa_key,
                algorithms=ALGORITHMS,
                audience=CLIENT_ID,
                issuer="https://" + DOMAIN + "/"
            )
        except jwt.ExpiredSignatureError:
            raise AuthError({"code": "token_expired",
                             "description": "token is expired"}, 401)
        except jwt.JWTClaimsError:
            raise AuthError({"code": "invalid_claims",
                             "description":
                                 "incorrect claims,"
                                 " please check the audience and issuer"}, 401)
        except Exception:
            raise AuthError({"code": "invalid_header",
                             "description":
                                 "Unable to parse authentication"
                                 " token."}, 401)

        return payload
    else:
        raise AuthError({"code": "no_rsa_key",
                         "description":
                             "No RSA key in JWKS"}, 401)


def error(err_string, err_code):
    return json.dumps({"Error": err_string}), err_code


def get_sub_from_jwt(jwt):
    parts = jwt.split('.')
    if len(parts) != 3:
        return error("Invalid JWT", 401)
    payload_str = base64.urlsafe_b64decode(parts[1] + '==').decode('utf-8')
    payload_dict = json.loads(payload_str)
    return payload_dict.get('sub', '')


def is_missing_attributes(content, required_attributes):
    for attribute in required_attributes:
        if attribute not in content:
            return True
    return False


def get_paginated_entities(entity_type, limit, offset, user=None):
    query = client.query(kind=getattr(constants, entity_type))
    if user:
        query.add_filter('user', '=', user)
    total_count = len(list(query.fetch()))
    iterator = query.fetch(limit=limit, offset=offset)
    pages = iterator.pages
    results = list(next(pages))
    next_url = None
    if iterator.next_page_token:
        next_offset = offset + limit
        next_url = f"{request.base_url}?limit={limit}&offset={next_offset}"
    for e in results:
        e["id"] = e.key.id
    return results, next_url, total_count


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
    return render_template('welcome.html')


@app.route('/login')
def login():
    return auth0.authorize_redirect(
        redirect_uri=url_for('callback', _external=True)
    )


@app.route('/callback', methods=['GET', 'POST'])
def callback():
    token = oauth.auth0.authorize_access_token()
    session["user"] = token
    resp = oauth.auth0.get('userinfo')
    userinfo = resp.json()
    session['jwt_payload'] = userinfo
    encoded_jwt = token.get('id_token')
    if encoded_jwt:
        user_sub = get_sub_from_jwt(encoded_jwt)
        user_key = client.key(constants.USERS, user_sub)
        user = client.get(user_key)
        if not user:
            new_user = datastore.Entity(key=user_key)
            new_user.update({
                'id': user_sub
            })
            client.put(new_user)
    return redirect('/user-info')


@app.route('/user-info')
def user_info():
    encoded_jwt = session.get('user').get('id_token')
    if not encoded_jwt:
        return error("No JWT found", 401)
    user_id = get_sub_from_jwt(encoded_jwt)
    return render_template('user_info.html', jwt=encoded_jwt, user_id=user_id)


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
        q_limit = int(request.args.get('limit', '5'))
        q_offset = int(request.args.get('offset', '0'))
        results, next_url, total_count = get_paginated_entities(
            "BOOKS", q_limit, q_offset)
        for book in results:
            book["self"] = get_self_url(book)
        output = {"books": results,
                  "count": total_count}
        if next_url:
            output["next"] = next_url
        return json.dumps(output)
    elif request.method == 'PUT' or request.method == 'DELETE':
        return error("Method not supported for this route", 405)
    else:
        return error('Method not recognized', 400)


@app.route('/books/<id>', methods=['GET', 'DELETE', 'PATCH', 'PUT'])
def books_get_delete_patch_put(id):
    book, error_msg = get_entity_by_id("BOOKS", int(id))
    if error_msg:
        return error(error_msg, 404)
    if request.method == 'GET':
        book["self"] = get_self_url(book)
        return json.dumps(book)
    elif request.method == 'DELETE':
        query = client.query(kind='reading_lists')
        reading_lists = list(query.fetch())
        for reading_list in reading_lists:
            if book["id"] in reading_list.get("books", []):
                reading_list["books"].remove(book["id"])
                client.put(reading_list)
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
        return error('Method not recognized', 400)


@app.route('/reading_lists', methods=['POST', 'GET'])
def reading_lists_post_get():
    if 'application/json' not in request.accept_mimetypes:
        return error("The server only sends JSON", 406)
    if request.method == 'POST':
        if request.content_type != 'application/json':
            return error("The server only accepts JSON", 415)
        try:
            payload = verify_jwt(request)
        except AuthError:
            return error("Unauthorized", 401)
        content = request.get_json()
        new_book = datastore.entity.Entity(key=client.key(
            constants.READING_LISTS))
        if is_missing_attributes(content, ["name", "description"]):
            return error("The request object is missing at least one of "
                         "the required attributes", 400)
        new_reading_list = update_entity(new_book,
                                         {"name": content["name"],
                                          "description": content["description"],
                                          "user": payload["sub"],
                                          "books": []})
        new_reading_list["self"] = get_self_url(new_reading_list)
        return json.dumps(new_reading_list), 201, {'Content-Type':
                                                   'application/json'}
    elif request.method == 'GET':
        try:
            payload = verify_jwt(request)
            user_sub = payload["sub"]
        except AuthError:
            return error("Unauthorized", 401)
        q_limit = int(request.args.get('limit', '5'))
        q_offset = int(request.args.get('offset', '0'))
        results, next_url, total_count = get_paginated_entities(
            "READING_LISTS", q_limit, q_offset, user_sub)
        for reading_list in results:
            reading_list["self"] = get_self_url(reading_list)
        output = {"reading_lists": results,
                  "count": total_count}
        if next_url:
            output["next"] = next_url
        return json.dumps(output)
    elif request.method == 'PUT' or request.method == 'DELETE':
        return error("Method not supported for this route", 405)
    else:
        return error('Method not recognized', 400)


@app.route('/reading_lists/<id>', methods=['GET', 'DELETE', 'PATCH', 'PUT'])
def reading_lists_get_delete_patch_put(id):
    reading_list, error_msg = get_entity_by_id("READING_LISTS", int(id))
    if error_msg:
        return error(error_msg, 404)
    try:
        payload = verify_jwt(request)
        user_sub = payload["sub"]
    except AuthError:
        return error("Unauthorized", 401)
    if reading_list.get('user') != user_sub:
        return error("Forbidden - Not owner of reading list", 403)
    if request.method == 'GET':
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
        return json.dumps(updated_reading_list), 200, {'Content-Type':
                                                       'application/json'}
    else:
        return error('Method not recognized', 400)


@app.route('/reading_lists/<reading_list_id>/books/<book_id>',
           methods=['PUT', 'DELETE'])
def books_put_delete(reading_list_id, book_id):
    reading_list, reading_list_error_msg = get_entity_by_id(
        "READING_LISTS", int(reading_list_id))
    book, book_error_msg = get_entity_by_id("BOOKS", int(book_id))
    if reading_list_error_msg or book_error_msg:
        return error("The specified reading_list "
                     "and/or book does not exist", 404)
    try:
        payload = verify_jwt(request)
        user_sub = payload["sub"]
    except AuthError:
        return error("Unauthorized", 401)
    if reading_list.get('user') != user_sub:
        return error("Forbidden - Not owner of reading list", 403)
    if request.method == 'PUT':
        if book["id"] not in reading_list.get("books", []):
            reading_list["books"] = reading_list.get("books", []) + [book["id"]]
            client.put(reading_list)
        else:
            return error("Book already in reading list", 400)
        return "", 204
    elif request.method == 'DELETE':
        if book["id"] not in reading_list.get("books", []):
            return error("The specified book is not in the reading list", 404)
        reading_list["books"] = [existing_book for existing_book in
                                 reading_list.get("books", [])
                                 if existing_book != book["id"]]
        client.put(reading_list)
        return "", 204
    else:
        return error('Method not recognized', 400)


@app.route('/reading_lists/<id>/books', methods=['GET'])
def get_books_in_reading_list(id):
    reading_list, reading_list_error_msg = get_entity_by_id(
        "READING_LISTS", int(id))
    if reading_list_error_msg:
        return error("The specified reading_list does not exist", 404)
    try:
        payload = verify_jwt(request)
        user_sub = payload["sub"]
    except AuthError:
        return error("Unauthorized", 401)
    if reading_list.get('user') != user_sub:
        return error("Forbidden - Not owner of reading list", 403)
    books_info = []
    for book_id in reading_list["books"]:
        book, book_error_msg = get_entity_by_id("BOOKS", book_id)
        if book_error_msg:
            return error(book_error_msg, 404)
        books_info.append(book)
    return json.dumps(books_info), 200


@app.route('/users', methods=['GET'])
def get_users():
    query = client.query(kind=constants.USERS)
    results = list(query.fetch())
    for e in results:
        e["id"] = e.key.name
    return json.dumps(results)


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080, debug=True)
