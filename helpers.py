# import requests
from pathlib import Path
from flask import redirect, render_template, session, current_app, url_for
import re
# import logging
# import time
import secrets
# import sqlite3
# from datetime import datetime
from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from email_validator import validate_email, EmailNotValidError
from functools import wraps
from db_helpers import clear_user_from_db, get_usage, get_db_handle, get_book_by_id, unlink_deck, unlink_decks4asin, unlink_decks, insert_deck, write_history_entry
from get_bookcover import *
from k2a_dictionaries import get_dictionaries 
from pyrae import dle
import requests
import logging
# import chardet 
from urllib.error import HTTPError
from urllib.parse import quote, unquote
from requests.adapters import HTTPAdapter
from requests.exceptions import RetryError
from kindle2anki import *
import genanki

def get_user_data_path(user_id: int | str) -> Path:
    user_dir = f"{int(user_id):06d}"
    return (
        Path(current_app.root_path)
        / "static"
        / "userdata"
        / user_dir
    )

def get_vocabdb_path(user_id: str) -> Path:
    return (
        get_user_data_path(user_id) / "vocab.db"
    )

def vocabdb_exists(user_id: str) -> bool:
    return get_vocabdb_path(user_id).is_file()

def is_sqlite_db(file):
    header = file.read(16)
    file.seek(0)
    return header == b"SQLite format 3\x00"

    return render_template("apology.html", top=code, bottom=escape(message)), code

def login_required(f):
    """
    Decorate routes to require login.

    https://flask.palletsprojects.com/en/latest/patterns/viewdecorators/
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)

    return decorated_function

def valid_name(name, logger):
    """validate name submitted for account creation"""
    isValid = True

    logger.info(f"check_name: received argument: '{name}'")
    # check if name is empty
    if not (name):
        message = "❌ Name is required"
        isValid = False
        return isValid, message

    name = name.strip().title()
    # check if name is made up of alphabetical chars and contains at least one word and not more than 4
    pattern = r"^([A-Za-z]{1,15}\s*){0,3}[A-Za-z]{1,15}$"
    if re.match(pattern, name):
        logger.info(f"name '{name}'matches pattern for valid names")
        message = re.sub(r'\s+', ' ', name)
    else:
        logger.error(f"name '{name}'does not match pattern for valid names")
        isValid = False
        message = f"❌ name '{name}'does not match pattern for valid names"

    return isValid, message

def valid_pw(pw1, pw2, logger):
    """validate submitted passwords for account creation"""
    logger.info(f"valid_pw: pw1: {pw1} pw2: {pw2}")
    messages = []

    # check if password and repeated password match
    if not (pw1):
        messages.append("❌ Password required")

    if not (pw2):
        messages.append("❌ Repeated password required")

    if (pw1 and pw2) and not secrets.compare_digest(pw1, pw2):
        logger.error(f"valid_pw: passwords {pw1} and {pw2} do not match")
        messages.append("❌ New password and repeated new password do not match")

    if (pw1) and (len(pw1) < 8):
        messages.append("❌ New password must contain at least 8 characters")

    if not any(char.isupper() for char in pw1):
        messages.append("❌ New password must contain at least one uppercase letter")

    if not any(char.isdigit() for char in pw1):
        messages.append("❌ New password must contain at least one number")

    if (messages):
        return False, messages
    else:
        return True, ""

def check_pw(db, logger, user_id, password):
    # Query database for hash
    logger.info(f"check_pw: checking password  ...")
    try:
        rows = db.execute("SELECT hash FROM users WHERE id = ?", user_id)
    except Exception as e:
        flash(f"❌ error reading hash form database: {e}", "error")
        return apology("Error reading hash from database", 400)

    # Ensure password is correct
    old_hash = rows[0]["hash"]
    logger.info(f"check_pw: checking password hash against db ...")
    if len(rows) != 1:
        flash(f"no hash found found in db", "error")
        return False

    if check_password_hash(old_hash, password):
        logger.info(f"password is correct")
        return True
    else:
        logger.info(f"password not correct")
        return False

def update_pw(db, logger, user_id, new_password):
    """ update user's password"""
    logger.info(f"update_pw: updating creating hash for password ...")
    hash = generate_password_hash(new_password)
    logger.info(f"update_pw: updating hash for {user_id} ...")
    try:
        db.execute("UPDATE users SET hash = ? WHERE id = ?", hash, user_id)
    except Exception as e:
        flash(f"❌ Failure to update password, a database error occured: {e}")
        return apology(f"Failure to update password, a database error occured: {e} ", 400)

    return True

def delete_account(db, user_id, logger):
    """ delete user by user_id"""
    logger.info(f"delete_user: deleting user {user_id} ...")
    # first clear all user data from db
    clear_user_from_db(db, user_id, logger)

    # then delete user's userdata folder
    clear_all(db, user_id, logger)
    return True

def clear_all(db, user_id, logger):
    user_data_path = get_user_data_path(user_id)
    logger.info(f"clear_all: deleting user data folder {user_data_path}")

    if not user_data_path.exists():
        logger.warning(f"User data path does not exist: {user_data_path}")
        flash(f"user data folder does not exist, nothing to delete", "warning")
        return False
    try:
        if user_data_path.is_dir():
            for item in user_data_path.iterdir():
                if item.is_file():
                    item.unlink()
            user_data_path.rmdir()
            logger.info(f"delete_user: deleted user data folder {user_data_path}")
            flash(f"✅ deleted user data folder ...", "success")
    except Exception as e:
        flash(f"❌ Failure to delete user's data folder, a filesystem error occured: {e}")
    session['vocabdb_uploaded'] = False

    unlink_decks(db, user_id, logger) 
    session['num_decks'] = 0
    return True

def clear_vocab_db(user_id, logger):
    """ delete user's vocab db file"""
    vocab_db_path = get_vocabdb_path(user_id)
    if not vocab_db_path.exists():
        logger.warning(f"User vocab_db_path does not exist: {vocab_db_path}")
        flash(f"✅ user vocab db file {vocab_db_path} does not exist, nothing to delete", "warning")
        return False
    try:
        if vocab_db_path.is_file():
            vocab_db_path.unlink()
            logger.info(f"clear_vocabdb: deleted vocab db file {vocab_db_path}")
            flash(f"✅ deleted user's vocab.db file", "success")
    except Exception as e:
        flash(f"❌ Failure to delete user's vocab db file, a filesystem error occured: {e}")  

    session['vocabdb_uploaded'] = False
    return True

def has_decks(user_id, logger):
    """Check if user has any .apkg deck files."""
    user_data_path = get_user_data_path(user_id)
    logger.info(f"has_decks: checking for decks for user {user_id} ...")

    if not user_data_path.exists():
        logger.warning(f"User data path does not exist: {user_data_path}")
        return False

    deck_files = list(user_data_path.glob("*.apkg"))
    if deck_files:
        session['num_decks'] = len(deck_files)
        logger.info(f"User {user_id} has {len(deck_files)} deck(s).")
        return True
    else:
        logger.info(f"User {user_id} has no decks.")
        session['num_decks'] = 0
        return False

def clear_decks(db, user_id, logger):
    """Delete all .apkg deck files for the given user."""
    user_data_path = get_user_data_path(user_id)
    logger.info(f"clear_decks: deleting all decks for user {user_id} ...")

    if not user_data_path.exists():
        logger.warning(f"User data path does not exist: {user_data_path}")
        return False

    deleted = 0

    for deck_file in user_data_path.glob("*.apkg"):
        try:
            deck_file.unlink()
            deleted += 1
            logger.info(f"Deleted deck file: {deck_file.name}")
        except Exception as e:
            logger.error(f"Failed to delete {deck_file}: {e}")

    # "unlink" user's decks in decks table
    unlink_decks(db, user_id, logger)
    session['num_decks'] = 0

    logger.info(f"clear_decks: deleted {deleted} deck(s) for user {user_id}")
    flash(f"✅ deleted {deleted} deck(s)", "success")
    return True

def clear_decks4asin(db, user_id, asin, logger):
    """Delete all .apkg deck files for the given user and asin."""
    user_data_path = get_user_data_path(user_id)
    logger.info(f"clear_decks: deleting all decks for user {user_id} and asin {asin}...")

    if not user_data_path.exists():
        logger.warning(f"User data path does not exist: {user_data_path}")
        return False

    deleted = 0

    for deck in user_data_path.glob(f"{asin}*.apkg"):
        try:
            deck.unlink()
            deleted += 1
            logger.info(f"Deleted deck file: {deck.name}")
        except Exception as e:
            logger.error(f"Failed to delete {deck}: {e}")

    # "unlink" user's decks in decks table
    unlink_decks4asin(db, user_id, asin, logger)
    session['num_decks'] -= deleted

    logger.info(f"clear_decks: deleted {deleted} deck(s) for user {user_id}")
    flash(f"✅ deleted {deleted} deck(s)", "success")
    return True 

def clear_single_deck(db, user_id, deck_id, deckname, logger):
    """Delete a single .apkg deck for the given user.
    naming convention being: asin.apkg"""
    # flash(f"clear_single_deck user_id: {user_id} deck_id: {deck_id} deckname: {deckname}...", "info")
    user_data_path = get_user_data_path(user_id)
    deck_file = user_data_path / f"{deckname}"
    logger.info(f"clear_decks: deleting deck {deck_file} for user {user_id} ...")

    if not user_data_path.exists():
        logger.warning(f"User data path does not exist: {user_data_path}")
        return False

    try:
        deck_file.unlink()
        logger.info(f"Deleted deck file: {deck_file.name}")
        session['num_decks'] -= 1
    except Exception as e:
        logger.error(f"Failed to delete {deck_file}: {e}")

    # 'unlink' deck in decks table
    unlink_deck(db, user_id, deck_id, logger)
    logger.info(f"unlink_deck: deleted deck with deck_id {deck_id}")
    flash(f"✅ deleted 1 deck", "success")
    return True

def get_book_cover(book, logger):
    """ get safe book cover url or default"""
    result = get_kindle_book_cover(book, size='S') 
    imagedir = Path(current_app.root_path) / "static" / "covers"
    if not imagedir.exists():
        imagedir.mkdir(parents=True, exist_ok=True)

    # Save cover
    if result.image_bytes:
        # safe_title = book['title'].replace(' ', '_').replace(':', '')
        # filename = f"{safe_title}.jpg"
        filename = f"{book['asin']}.jpg"
        imagepath = imagedir / filename
        with open(f"{imagepath}", "wb") as f:
            f.write(result.image_bytes)
            logger.info(f"safe_book_cover: saved cover as {imagepath}")  
    """ return safe book cover url or default"""
    if result is None:
        logger.info(f"safe_book_cover: no cover found, using default")
        return "/static/img/book_cover_default.png"
    else:
        logger.info(f"safe_book_cover: using found cover")
        return filename

def select_dict(lang, logger):
    # flash('select_dict called', 'info')
    # flash(f'calling get_dictionaries for lang {lang}', 'info')
    dictionaries = get_dictionaries(lang)
    # flash(f'found {len(dictionaries)} dictionaries for lang {lang}', 'info')
    # flash(f'dictionaries: {dictionaries}', 'info')
    if not dictionaries:
        flash(f'No dictionaries found for language {lang}', 'error')
        logger('select_dict: No dictionaries found', 'error')
        return None
    return dictionaries

def select_card_type(lang, logger):
    pass

def create_card_deck(db, vdb, deck_request, logger):
    from kindle2anki import connect, get_definitions, get_definitions_rae, create_deck, create_cards 
    # flash(f'create_card_deck called with {deck_request}', 'info')
    tables = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    # flash(f'create_card_deck - tables: {tables}')
    # read values from deck_request
    book_id = deck_request['book_id']
    dict_id = deck_request['dict_id']
    card_type = deck_request['card_type']
    # flash(f'deck_request processed ...)', 'info')
    user_id = session['user_id']
    # get vocatb db path

    # get book info
    # flash(f'calling get_book_by_id book id {book_id} ...', 'info')
    book = get_book_by_id(db, vdb, book_id, logger)

    # get book language
    lang = book['lang']

    # get dictionary info
    # flash(f'calling get_dictionaries for lang {lang} ...', 'info')
    dictionaries = get_dictionaries(lang)
    # flash(f'found {len(dictionaries)} dictionaries for lang {lang} ...', 'info')
    # flash(f'dictionaries: {dictionaries} ...', 'info')
    dict_id = int(dict_id)
    dict = next((d for d in dictionaries if d['id'] == dict_id), None)
    if dict is None:
        flash(f'No dictionary found for id {dict_id}', 'error')
        return None
    # flash(f'Using dictionary: {dict}', 'info')
    # special handling for RAE dictionary
    if dict['url'] == 'https://dle.rae.es/':
        rae = True
    else:
        rae = False

    # get usage info for words looked up in this book
    # flash(f'getting usage info for book {book["title"]} ...', 'info')
    usage = get_usage(vdb, book)
    # for convenience get the words (keys of usage) as a list
    words = list(usage.keys())

    num_log_level = 6
    string_log_level = 'info'
    # establish a connection to the dictionary URL of the chosen dictionary
    flash(f'establishing connection to dictionary {dict["name"]} ...', 'info')
    if rae == False:
        s = connect(dict['url'], dict['referer'], num_log_level)

        # retrieve dictinary definitions for the words in our book that were looked up in kindle
        flash(f'retrieving definitions from dictionary {dict["name"]} ...', 'info')
        titles, definitions = get_definitions(s, dict, words, num_log_level, logger)

        # close the https session
        s.close()
    else:
        # connection will be handled by pyrae module
        titles, definitions = get_definitions_rae(words, string_log_level, logger)


    # create the anki card deck
    flash(f'creating anki deck for book {book["title"]} ...', 'info')

    deck_internal_name = f'{book['authors']} - {book['title']}'
    deckname = f"{book['asin']}_{book['lang']}_{dict_id}.apkg"
    deckpath = get_user_data_path(session['user_id']) / deckname
    # flash(f'creating deck {deckname} ...', 'info')
    deck = create_deck(deck_internal_name, logger)

    # add cards to the card deck (of the chosen card type, one per word)
    flash(f'adding cards to deck {deckname}...', 'info')
    has_cards, cards = create_cards(deck, dict, card_type, words, usage, titles, definitions, logger)
    # flash(f'create_card_decks: obtained has_cards: {has_cards} cards:  {cards}...', 'warning')
    if has_cards == False:
        flash(f'Too bad - no definitions found in selected dictionary for words in selected book!', "error")
        return has_cards 
    # write out card deck to a apkg file
    flash(f'writing out card deck to <your_userdata_directory>/{deckname}...', 'info')
    logger.info(f'writing out card deck to {deckpath}...')
    genanki.Package(deck).write_to_file(deckpath)

    # insert record to deck table
    asin = book['asin']
    deck_id = insert_deck(db, user_id, asin, deckname, cards, logger)
    user_dir = f"{int(user_id):06d}"
    # download_url = url_for('static', filename=f"userdata/{user_dir}/{deckname}")

    # insert record to history table
    timestamp = int(time.time())
    write_history_entry(db, user_id, deck_id, dict_id, book['authors'], book['title'], book['lang'], timestamp, logger)
    # flash(f'create_card_deck: returning book {book} and cards {cards}')
    return book, cards, deck_id

def get_language_name(lang_code):
    lang_map = {
        'en': 'English',
        'de': 'German',
        'fr': 'French',
        'es': 'Spanish',
        'pt': 'Portuguese'
    }
    return lang_map.get(lang_code.lower(), 'Unknown')   

def iconify_language(text: str) -> str:
    """Replace language codes with emoji flags (case-insensitive)."""
    mapping = {
        'de': '🇩🇪',
        'en': '🇬🇧',
        'fr': '🇫🇷',
        'es': '🇪🇸',
        'pt': '🇵🇹',
    }

    def repl(match):
        return mapping[match.group(0).lower()]

    return (
        re.sub(r'\b(de|en|fr|es|pt)\b', repl, text, flags=re.IGNORECASE)
        .replace('->', ' ⇨ ')
        .replace('<-', ' ⇦ ')
    )

def describe_card_type(card_type: str) -> str:
    """return human readable description of card type."""
    card_type_map = {
        'A': 'Front (Word + text passage from ebook) / Back (Definitions + Usage examples)',
        'B': 'Front: (definitions) / Back: (word + text passage from ebook)',
    }
    return card_type_map.get(card_type, 'Unknown Card Type')    

def deck_status(file_exists):
    if file_exists == 1:
        return "exists"
    else:
        return "deleted"