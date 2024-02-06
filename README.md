# reading-list-api
A Flask-based web API for managing reading lists and books, complete with user 
registration and authentication via Auth0. Created as a portfolio project for
CS 493: Cloud Application Development at Oregon State University.

## Docs
Read the API documentation **[here](reading_list_api_docs.pdf)**.

## Supported Operations
- `POST /books` - Create a Book
- `GET /books` - View all Books
- `GET /books/:book_id` - View a Book
- `DELETE /books/:book_id` - Delete a Book
- `PATCH /books/:book_id` - Edit a Book
- `PUT /books/:book_id` - Edit a Book
- `POST /reading_lists` - Create a Reading List
- `GET /reading_lists` - View all Reading Lists
- `GET /reading_lists/:reading_list_id` - View a Reading List
- `DELETE /reading_lists/:reading_list_id` - Delete a Reading List
- `PATCH /reading_lists/:reading_list_id` - Edit a Reading List
- `PUT /reading_lists/:reading_list_id` - Edit a Reading List
- `PUT /reading_lists/:reading_list_id/books/:book_id` - Add a Book to a Reading List
- `DELETE /reading_lists/:reading_list_id/books/:book_id` - Remove a Book from a Reading List
- `GET /reading_lists/:reading_list_id/books` - View all Books in a Reading List
- `GET /users` - View all Users