# imports
# import re
# import logging
# import time
# import secrets
# import sqlite3
import os
from datetime import datetime
from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, url_for, current_app, send_file, abort
from flask_session import Session
from werkzeug.security import check_password_hash 
from email_validator import validate_email, EmailNotValidError
from get_bookcover import *
from helpers import *
from db_helpers import *

# Configure application
app = Flask(__name__)
app.secret_key = os.urandom(24)
logger = app.logger

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = db_setup(logger, "k2a.db")

# supported languages
SUPPORTED_LANGUAGES = ['en', 'de', 'fr', 'it', 'es', 'pt']

# Custom filters
app.jinja_env.filters["get_lang_name"] = get_language_name
app.jinja_env.filters["iconify_lang"] = iconify_language
app.jinja_env.filters["describe_card_type"] = describe_card_type

# definition of routes
@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        # user submitted registration form
        errors = []  # record errors in array of strings

        # check name
        username = request.form.get("username", "")
        # valid, message = valid_name(request.form.get("username", ""), logger)
        # if not valid:
        #    errors.extend(message)
        # else:
        #    username = message

        # check email
        email = request.form.get("email", "").strip()
        try:
            # Validate and get normalized email
            valid = validate_email(email)
            email_normalized = valid.email
            print(f"Valid: {email_normalized}")
        except EmailNotValidError as e:
            errors.append(f"❌ Invalid email {email}, {str(e)}")
        # check passwords
        pw1 = request.form.get("password", "")
        pw2 = request.form.get("confirmation", "")
        valid, messages = valid_pw(pw1, pw2, logger)

        if not valid:
            errors.extend(messages)

        if errors:
            for error in errors:
                flash(error, "error")
            return apology("look above for errors", 400)
        else:
            app.logger.info(f"adding user {username}")
            row_id, message = insert_user(username, email_normalized, pw1, db, logger)
            logger.info(f"row_id: {row_id} message: {message}")

            if (row_id):
                session.clear()
                session["user_id"] = row_id
                session["username"] = username
                session["email"] = email_normalized
                flash(
                    f"Sucessfully created account. You are now logged in as user {username}({email_normalized})", "success")
                # return render_template("index.html")
                return redirect("/")
            else:
                # return render_template("register.html")
                flash(f"{message}", "error")
                return redirect(request.url)

    else:
        # user reached route via get
        return render_template("register.html")

    return apology("Neither GET nor POST - THIS SHOULD NEVER HAPPEN", 400)

@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    """ first get user_id from session """
    user_id = session['user_id']

    if request.method == "POST":
        actions = {
            "delete_account": delete_account,
            "clear_all": clear_all,
            "clear_vocab_db": clear_vocab_db,
            "clear_decks": clear_decks
        }
        action = request.form.get("action", "")

        func = actions.get(action)
        if not func:
            flash("Invalid action requested", "error")
            return redirect(request.url)

        try:
            if func == delete_account:
                func(db, user_id, logger)
                session.clear()
                flash(f"✅ Action '{action}' completed successfully. Your account has been deleted.", "success")
                return redirect("/login")
            elif func == clear_vocab_db:
                func(user_id, logger)
                flash(f"✅ Action '{action}' completed successfully", "success")
            else:
                func(db, user_id, logger)
                flash(f"✅ Action '{action}' completed successfully", "success")
        except Exception as e:
            logger.exception(e)
            flash(f"Failed to perform action '{action}'", "error")

    # stuff to do for both GET and POST
    """ check for vocab.db file """
    if not vocabdb_exists(str(user_id)):
        session['vocabdb_uploaded'] = False
        flash(f"You have not yet uploaded a vocab.db file - please upload one", "info")
    else:
        flash(f"✅ vocab.db file found", "info")
        session['vocabdb_uploaded'] = True

    """check for card decks"""
    session['has_decks'] = has_decks(user_id, logger)
    if session['has_decks']:
        flash(f"✅ {session['num_decks']} card deck(s) found", "info")
    else:
        flash(f"✖️ no card decks found", "info") 

    return render_template("index.html")
    
@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    """ Upload vocab.db """
    if request.method == "POST":
        if 'vocab_db' not in request.files:
            flash('No file part', 'error')
            return redirect(request.url)
        file = request.files['vocab_db']
        # check if user selected a file
        if file.filename == '':
            flash('No selected file', 'error')
            return redirect(request.url)   
            # Redirect user to home page
            return redirect("/")
        # check if the uploaded file is named vocab.db
        if file.filename != 'vocab.db':
            flash('Invalid file name. Please upload a file named vocab.db', 'error')
            return redirect(request.url)
        # check if the file is a valid sqlite3 database
        if not is_sqlite_db(file):
            flash('Uploaded file is not a valid SQLite database', 'error')
            return redirect(request.url) 

        # save the file to the user's userdata directory
        user_id = session['user_id']
        upload_path = get_user_data_path(user_id)
        upload_path.mkdir(parents=True, exist_ok=True)
        file_path = upload_path / "vocab.db"
        file.save(file_path)
        flash(f"✅ Successfully uploaded vocab.db", "success")
        session['vocabdb_uploaded'] = True
        # return render_template("create.html")
        return redirect("/create")
    else:
        # we got here via GET
        return render_template("upload.html")

@app.route("/create", methods=["GET", "POST"])
@login_required
def create():
    """ get user_id from session """
    user_id = session['user_id']
    vocab_db = get_vocabdb_path(user_id)
    vdb = get_db_handle(vocab_db, logger)
    if vdb is None:
        flash("Could not read vocab.db", "error")
        return redirect(request.url)

    if request.method == "POST":
        actions = {
            "clear4asin": clear_decks4asin,
            "select_dict": select_dict,
            "select_card_type": select_card_type,
            "create_card_deck": create_card_deck
        }
        action = request.form.get("action", "")

        func = actions.get(action)
        if not func:
            flash("Invalid action requested", "error")
            return redirect(request.url)

        try:
            if func == clear_decks4asin:
                asin = request.form.get("asin", "")
                if not asin:
                    flash("No ASIN provided for delete action", "error")
                    return redirect(request.url)
                func(db, user_id, asin, logger)
            elif func == select_dict:
                book_id = request.form.get("book_id", "")
                if not book_id:
                    flash(f"No book provided for action {action}", "error")
                    return redirect(request.url)
                lang = request.form.get("lang", "")
                if not lang:
                    flash(f"No book language provided for action {action}", "error")
                    return redirect(request.url)
                # flash(f"calling func {func} with lang {lang}", "info")
                dictionaries = func(lang, logger)
                if dictionaries is None:
                    flash(f"No dictionaries found for book {book_id} in language {lang}", "error")
                    return redirect(request.url)
                # flash(f"dictionaries: {dictionaries}", "info")
                book = get_book_by_id(db, vdb, book_id, logger)
                if not book:
                    flash(f"Could not get book info for book id {book_id}", "error")
                    return redirect(request.url)
                return render_template("create.html", book=book, dictionaries=dictionaries)

            elif func == select_card_type:
                book_id = request.form.get("book_id", "")
                if not book_id:
                    flash(f"No book_id provided for action {action}", "error")
                    return redirect(request.url)
                dict_id = request.form.get("dict_id", "")
                if not dict_id:
                    flash(f"No dict_id provided for action {action}", "error")
                    return redirect(request.url)
                # get book info
                book = get_book_by_id(db, vdb, book_id, logger)
                if not book:
                    flash(f"Could not get book info for book id {book_id}", "error")
                    return redirect(request.url)
                # get lang from book
                lang = book['lang']
                if not lang:
                    flash(f"No book language provided for action {action}", "error")
                    return redirect(request.url)
                # get dictionary for lang and dict_id
                dicts = get_dictionaries(lang)
                dict = next((d for d in dicts if d['id'] == int(dict_id)), None)
                # flash(f"dict: {dict}", "info")
                if not dict:
                    flash(f"Could not get dictionary info for dict id {dict_id}", "error")
                    return redirect(request.url)
                return render_template("create.html", book=book, dict=dict)
            elif func == create_card_deck:
                deck_request = {
                    'book_id': request.form.get("book_id", ""),
                    'dict_id': request.form.get("dict_id", ""),
                    'card_type': request.form.get("card_type", ""),
                }
                # validate deck_request
                missing_fields = [key for key, value in deck_request.items() if not value]
                if missing_fields:
                    flash(f"Missing fields for create_deck: {', '.join(missing_fields)}", "error")
                    return redirect(request.url)

                # flash(f"calling func {func} with deck_request {deck_request}", "info"  )
                book, cards, deck_id = func(db, vdb, deck_request, logger)
                dicts = get_dictionaries(book['lang'])
                dict = next((d for d in dicts if d['id'] == int(deck_request['dict_id'])), None)
                session['has_history'] = has_history(db)
                flash(f"✅ Successfully created deck for book {book['title']}", "success")
                return render_template("create.html", card_type = deck_request["card_type"], book=book, dict=dict, cards=cards, deck_id=deck_id)
            else:
                pass
        except Exception as e:
            logger.exception(e)
            flash(f"Failed to perform action '{action}, error: {e}'", "error")
        return redirect(request.url)

    else:
        books = get_books_from_vocabdb(db, vdb, logger)
        if books is None:
            flash("Could not read books from vocab.db", "error")
            return redirect(request.url)
        # get book covers
        # flash(f"Getting book covers ...", "info")
        for book in books:
            #  logger.info(f"book: {book}")
            image = book['asin'] + ".jpg"
            imagepath = Path(current_app.root_path) / "static" / "covers" / image
            #  logger.info(f"book cover path: {imagepath}")
            if not imagepath.exists():
                image = get_book_cover(book, logger)
            book['cover'] = url_for('static', filename=f"covers/{image}")   
            logger.info(f"book cover: {book['cover']}") 
        return render_template("create.html" , books=books)

@app.route("/history", methods=["GET", "POST"])
@login_required
def history():
    user_id = session['user_id']
    if request.method == 'POST':
        # flash(f'history called via post ...', 'info')
        deck_id = request.form.get("deck_id", "")
        deckname = request.form.get('deckname', "")
        # flash(f'user_id: {user_id} deck_id: {deck_id}  deckname: {deckname}')
        if deck_id and deckname:
            try:
                clear_single_deck(db, user_id, deck_id, deckname, logger)
            except Exception as e:
                flash(f'error deleting deck with id {deck_id}: {e}')

    """Show history of transactions"""
    try:
        rows = show_history(db)
    except Exception as e:
        flash(f"Could not retrieve db records from history: {e}", "error")
        return redirect("/")

    if (rows):
        history = []
        for row in rows:
            record = dict(row)
            record['time'] = datetime.fromtimestamp(record['timestamp'])
            dicts = get_dictionaries(record['lang'])
            record['dict'] = next((d for d in dicts if d['id'] == record['dict_id']), None)
            # flash(f'history: {record['dict']}')
            if record['file_exists'] == 1:
                user_id = session['user_id']
                user_dir = f'userdata/{user_id:06d}'
                link = url_for("static", filename=f"{user_dir}/{record['deckname']}")
                record['file_exists'] = link
            history.append(record)
        return render_template("history.html", history=history)
    else:
        return render_template("history.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        token = request.form.get("username")
        if not token:
            flash("you must provide a username or email address", "error")
            return render_template("login.html")

        # Determine if token is an email or username
        if "@" in token:
            rows = db.execute(
                "SELECT username FROM users WHERE email = ?", token
            )
            if len(rows) != 1:
                flash("unknown email", "error")
                return render_template("login.html")
            username = rows[0]['username']
        else:
            username = token

        # Ensure password was submitted
        if not request.form.get("password"):
            flash("you must provide a password", "error")
            return render_template("login.html")

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", username
        )
        if len(rows) != 1:
            flash("unknown username", "error")
            return render_template("login.html")

        # Ensure username exists and password is correct
        if not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            flash("invalid password", "error")
            return render_template("login.html")

        # Remember which user has logged in
        session['user_id'] = rows[0]['id']
        session['email'] = rows[0]['email']
        session['username'] = username
        session['has_history'] = has_history(db)

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")

@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")

@app.route("/changepw", methods=['GET', 'POST'])
@login_required
def change_pw():
    """Change user password"""
    user_id = session['user_id']
    if request.method == "POST":
        errors = []
        password = request.form.get('password', "")
        new_password = request.form.get('new_password', "")
        repeated_new_password = request.form.get('repeated_new_password', "")
        logger.info(
            f"password: {password} new_password: {new_password} repeated_new_password: {repeated_new_password}")

        if not (password):
            errors.append(f"❌ Old password not provided")

        if not (new_password):
            errors.append(f"❌ New password not provided")

        if not (repeated_new_password):
            errors.append(f"❌ Repeated new password not provided")

        # check old pw
        if not check_pw(db, logger, user_id, password):
            errors.append(f"❌ Incorrect old password")

        # check if new pw and repeated new pw match
        logger.info(f"calling valid_pw for new_password and repeated_new_password")
        valid, messages = valid_pw(new_password, repeated_new_password, logger)
        if not valid:
            errors.extend(messages)

        # check if old pw and new-pw match (here we have to invert the logig of valid)
        logger.info(f"calling valid_pw for password and new_password")
        valid, messages = valid_pw(password, new_password, logger)
        if (valid):
            errors.append(f"❌ Old and new password must not be identical")
        else:
            logger.info(f"messages: {messages}")

        if errors:
            for error in errors:
                flash(error, "error")
            return render_template("changepw.html")

        # update pw
        if update_pw(db, logger, user_id, new_password):
            flash(f"Successfully updated your password ...", "success")
            return redirect("/")
    else:
        return render_template("changepw.html")

@app.route("/download/decks/<int:deck_id>")
@login_required
def download_deck(deck_id):
    user_dir = f"{int(session['user_id']):06d}"
    deck_id = int(deck_id)
    # flash(f'received deck_id {deck_id}')
    deck = get_deck_by_id(db, deck_id, logger)
    if not deck:
        flash("no deck of yours found with deck_id {deck_id}", "error")

    deckname = deck['deckname']
    lang = deck['lang'].upper()
    authors = deck['authors']
    if ', ' in authors:
        last, first = authors.split(', ')
        authors = first + ' ' + last
    title = deck['title']

    filepath = (
    Path(current_app.root_path)
    / "static"
    / "userdata"
    / user_dir
    / deckname
    )

    if not filepath.exists():
        abort(404)

    # download_name= f"{lang}_{authors}_{title}.apkg"
    download_name= f"{authors} - {title}.apkg"

    return send_file(
        filepath,
        as_attachment=True,
        download_name=download_name
    )

    return redirect(url_for('history'))