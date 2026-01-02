# db_helpers.py - functions to help with db setup and management

# imports
import os
import sqlite3
from cs50 import SQL
from flask import flash, redirect, request, session, url_for
from pathlib import Path
from werkzeug.security import generate_password_hash

# function to make sure the db exists with all required tables
def db_setup(logger, db_name):
    # create db if it does not exist
    if not os.path.exists(db_name):
        logger.info(f"Creating database {db_name}...")
        try:
            conn = sqlite3.connect(db_name)
            conn.close()
            logger.info(f"Created database {db_name}")
        except Exception as e:
            logger.error(f"ERROR: Failed to create database{db_name}: {e}")
    else:
        logger.info(f"database {db_name} already exists")

    # connect to db using CS50 module and then return db handle
    db = SQL(f"sqlite:///{db_name}")

    # create tables if they do not exist
    """create user table if not exists"""
    try:
        db.execute("""
        CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
        username TEXT NOT NULL,
        email TEXT NOT NULL CHECK(email LIKE '%_@__%.__%'),
        hash TEXT NOT NULL,
        UNIQUE(username, email)
        )
        """)
    except Exception as e:
        logger.error(f"Failed to create table users")
        flash(f"❌ a database error occured: {e}")
        return redirect(request.url)

    """create decks table if not exists"""
    try:
        db.execute("""
        CREATE TABLE IF NOT EXISTS decks (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER NOT NULL,
        asin         TEXT NOT NULL,
        deckname     TEXT NOT NULL,
        cards        INTEGER NOT NULL CHECK (cards > 0),
        file_exists  INTEGER NOT NULL DEFAULT 1
                     CHECK (file_exists IN (0, 1)),
        FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """)
    except Exception as e:
        flash(f"❌ a database error occured: {e}")
        return redirect(request.url)
    
    """create history table if not exists"""
    try:
        db.execute("""
        CREATE TABLE IF NOT EXISTS history (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id      INTEGER NOT NULL,
        deck_id      INTEGER NOT NULL,
        dict_id      INTEGER NOT NULL,
        authors      TEXT NOT NULL,
        title        TEXT NOT NULL,
        lang         TEXT NOT NULL CHECK (lang in('en', 'de', 'fr', 'es', 'pt')),
        timestamp    INTEGER NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (deck_id) REFERENCES decks(id)
        )
        """)
    except Exception as e:
        flash(f"❌ a database error occured: {e}")
        return redirect(request.url)

    # return db handle
    return db

# function to insert a new user into the users table
def insert_user(username, email, password, db, logger):
    """Insert a new user with hashed password"""

    # check if user with this name already exists
    try:
        rows = db.execute("SELECT id FROM users WHERE username = ?", username)
    except Exception as e:
        flash(f"insert_user: database error: {e}", "error")
        return None, f"Database error: {e}"

    if (rows):
        return None, f"user {username} already exists"

    hashed_pw = generate_password_hash(password)
    logger.info(f"hashed pw is: {hashed_pw}")
    row_id = None
    try:
        row_id = db.execute("INSERT INTO users (username, email, hash) VALUES (?, ?, ?)", username, email, hashed_pw)
        logger.info(f"sucessfully added user {username} with row_id {row_id}")
    except Exception as e:
        flash(f"❌ a database error occured: {e}")
        return None, f"Failed to add user {username} to users, database error: {e}"
    return row_id, f"sucessfully added user {username} with row_id {row_id}"

def insert_deck (db, user_id, asin, deckname, cards, logger):
    """ insert new deck to decks table"""
    # flash(f'insert_deck running with db_handle {db}...')
    # get all table names
    try:
        # flash(f"inserting into decks ")
        row_id = db.execute(
            "INSERT INTO decks (user_id, asin, deckname, cards) VALUES (?, ?, ?, ?)", 
            user_id, asin, deckname, cards
        )
        logger.info(f"sucessfully added deck for user_id {user_id}, deckname {deckname} with row_id {row_id}")
    except Exception as e:
        flash(f"❌ a database error occured: {e}")
        logger.error(f'Failed to add deck for user_id {user_id} and deckname {deckname}to decks, database error: {e}')
        return None
    
    # since a new deck for the deckname was created, any previous deck will have been overwritten.
    try:
        db.execute(
            "UPDATE decks SET file_exists = 0 WHERE user_id = ? AND deckname = ? AND id != ?", 
            user_id, deckname, row_id
        )
    except Exception as e:
        logger.error(f'Failure to update db records in decks: {e}')

    return row_id

# set all decks of a user to deleted
def unlink_decks(db, user_id, logger):
    try:
        db.execute(
            "UPDATE decks SET file_exists = 0 WHERE user_id = ?", user_id)
    except Exception as e:
        logger.error(f'Failure to clear decks for user: {e}')
        return False

    return True

def unlink_decks4asin(db, user_id, asin, logger):
    try:
        db.execute(
            "UPDATE decks SET file_exists = 0 WHERE user_id = ? and asin = ?", user_id, asin)
    except Exception as e:
        logger.error(f'Failure to update records in decks: {e}')
        return False

    return True


# set deck with a particular asin to deleted
def unlink_deck(db, user_id, deck_id, logger):
    try:
        db.execute("UPDATE decks SET file_exists = 0 WHERE user_id = ? and id = ?", user_id, deck_id)
    except Exception as e:
        flash(f'unlink_deck: failure to update record with deck_id {deck_id}: {e}')
        logger.error(f'Failure to update records in decks: {e}')

# function to delete user from db
def clear_user_from_db(db, user_id, logger):
    """ delete user by user_id"""
    logger.info(f"delete_user: deleting user {user_id} ...")

    # first delete all decks for this user
    try:
        db.execute("DELETE FROM decks WHERE user_id = ?", user_id)
    except Exception as e:
        flash(f"❌ Failure to delete user's decks, a database error occured: {e}")
    # then delete all history for this user
    try:
        db.execute("DELETE FROM history WHERE user_id = ?", user_id)
    except Exception as e:
        flash(f"❌ Failure to delete user's history, a database error occured: {e}")    
    # finally delete form user table
    try:
        db.execute("DELETE FROM users WHERE id = ?", user_id)
    except Exception as e:
        flash(f"❌ Failure to delete user, a database error occured: {e}")

# function to read books from vocab db
def get_books_from_vocabdb(db, vdb, logger, lang=None):
    user_id = session['user_id']
    # lang must e one of 'EN', 'DE', 'FR', 'PT', 'ES' or None
    supported_langs = ['en', 'de', 'fr', 'es', 'pt']
    if lang and lang not in supported_langs:
        flash(f"❌ invalid language code {lang} specified", "error")
        return []
    try:
         # get keys of books for which we have looked up vocab
        key_result = vdb.execute("SELECT DISTINCT(book_key) FROM LOOKUPS")
        book_keys = [key['book_key'] for key in key_result]
        # flash(book_keys, "info")
        # flash(supported_langs, "info")
        if lang == None:
            """ read books from vocab db without language filter"""
            logger.info(f"get_books_from_vocabdb: reading books from vocab db ...")
            SQL_query = "SELECT id, lang, asin, title, authors FROM BOOK_INFO WHERE id IN (?) and lang in (?) ORDER BY lang, authors, title"
            books = vdb.execute(SQL_query, book_keys, supported_langs)
        else:
            SQL_query = "SELECT id, lang, asin, title, authors FROM BOOK_INFO WHERE id in (?) AND lang = ? ORDER BY lang, authors, title"
            """ read books from vocab db with language filter"""
            logger.info(f"get_books_from_vocabdb: reading books from vocab db for language {lang} ...")
            books = vdb.execute(SQL_query, book_keys, lang)

        # add cover path to each book
        for book in books:
            cover = book['asin'] + ".jpg"
            book['cover'] = url_for('static', filename=f"covers/{cover}")   
            # user_dir = f"{int(user_id):06d}"
            # apkg = book['asin'] + ".apkg"
            # book['apkg'] = url_for('static', filename=f"userdata/{user_dir}/{apkg}")

        # get number of looked up words for each book
        for book in books:
            id = book['id']
            num_lookups = list(vdb.execute("SELECT COUNT(DISTINCT(word_key)) FROM LOOKUPS WHERE book_key = ?", id)[0].values())[0]
            book['num_lookups'] = num_lookups
            # check if decks have been created already for this book
            book['num_decks'] = has_decks4asin(db, book['asin'])

        # check for apkg file 
        # from helpers import get_user_data_path
        # user_dir = f"{int(user_id):06d}"
        # for book in books:
        #     asin = book['asin']
        #     apkg_path = get_user_data_path(user_id) / f"{asin}.apkg"
        #     apkg_flask_path = Path("userdata" , f'{user_dir}' , f"{asin}.apkg")
        #     if apkg_path.exists():
        #         book['apkg'] = apkg_flask_path
        #         # flash(f"Found apkg for book {book['title']} at {apkg_path}", "info")
        #     else:
        #         book['apkg'] = None

    except Exception as e:
        flash(f"❌ error reading books from vocab db: {e}", "error")
        return []

    logger.info(f"get_books_from_vocabdb: found {len(books)} books in vocab db")
    flash(f"✅ found {len(books)} books in vocab db", "info")
    return books

# get database handle
def get_db_handle(vocab_db_path, logger):
    """ get database handle for vocab db"""
    logger.info(f"get_db_handle: getting database handle for vocab db {vocab_db_path} ...")
    try:
        db = SQL(f"sqlite:///{vocab_db_path}")
    except Exception as e:
        flash(f"❌ error reading vocab db: {e}", "error")
        return None
    return db

def get_book_by_id(db, vdb, book_id, logger):
    """ get book info by book_id from vocab db"""
    user_id = session['user_id']
    try:
        SQL_query = "SELECT id, lang, asin, title, authors FROM BOOK_INFO WHERE id = ?"
        result = vdb.execute(SQL_query, book_id)
        if len(result) == 0:
            flash(f"get_book_by_id: ❌ book with id {book_id} not found in vocab db", "error")
            return None
        book = result[0]
        # get number of looked up words for this book
        id = book['id']
        num_lookups = list(vdb.execute("SELECT COUNT(DISTINCT(word_key)) FROM LOOKUPS WHERE book_key = ?", id)[0].values())[0]
        book['num_lookups'] = num_lookups
        cover = book['asin'] + ".jpg"
        book['cover'] = url_for('static', filename=f"covers/{cover}")  
        book['num_decks'] = has_decks4asin(db, book['asin']) 
        return book
    except Exception as e:
        logger.error(f'get_book_by_id: error retrieving book from vocab.db: {e}')
        flash(f"get_book_by_id: ❌ error reading book from vocab db: {e}", "error")
        return None
    
def get_usage(db, book_id): # retrieve text passages with looked-up words from kindle db
    """
    :param db :     the sqllite database-handle to the kindle database
    :param book:    the book selected 
    :return usage:  a dictionary with the looked-up words as keys and 'usages' (i.e. the text passages 
                    in the e-book) where the looked-up word occured as values
    """
    usage = {}
    worddicts = db.execute("SELECT word_key, usage FROM LOOKUPS WHERE book_key = ?", book_id)
    for worddict in worddicts:
        word = worddict['word_key'].split(':')[1]
        if not word in usage:
            usage[word] = worddict['usage'].replace(word, f"<b>{word}</b>")
    return usage

def write_history_entry(db, user_id, deck_id, dict_id, authors, title, lang, timestamp, logger):
    #write_history_entry(db, user_id, deck_id, book['authors'], book['title'], book['num_lookups'], timestamp, logger)
    """ write an entry into the history table"""
    try:
        db.execute("""
        INSERT INTO history (user_id, deck_id, dict_id, authors, title, lang, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, user_id, deck_id, dict_id, authors, title, lang, timestamp)
        logger.info(f"wrote history entry for user {user_id}, deck {deck_id},")
    except Exception as e:
        flash(f"❌ a database error occured while writing history entry: {e}", "error")

def show_history(db):
    user_id = session['user_id']
    query = """SELECT
            h.deck_id,
            h.dict_id,
            h.authors,
            h.title,
            h.lang,
            MAX(h.timestamp) AS timestamp,
            d.deckname,
            d.cards,
            d.file_exists
            FROM history h
            JOIN decks d
            ON d.id = h.deck_id
            WHERE h.user_id = ?
            GROUP BY h.deck_id
            ORDER BY h.timestamp DESC"""
    try:
        result = db.execute(query, user_id)
    except Exception as e:
        flash(f"❌ a database error occured while writing history entry: {e}", "error")

    return result

def has_history(db):
   user_id = session['user_id'] 
   query = "SELECT 1 FROM history WHERE user_id = ? LIMIT 1;"
   result = db.execute(query, user_id)
   return result is not None

def has_decks4asin(db, asin):
    user_id = session['user_id']
    query = """
        SELECT COUNT(*) AS num_decks
        FROM decks
        WHERE user_id = ? AND asin = ? AND file_exists = '1';
    """
    result = db.execute(query, user_id, asin)
    return result[0]["num_decks"]

def get_deck_by_id(db, deck_id, logger):
    user_id = session['user_id']
    deck_id = int(deck_id)
    query = """SELECT
                h.dict_id,
                h.authors,
                h.title,
                h.lang,
                d.deckname
            FROM history h
            JOIN decks d ON d.id = h.deck_id
            WHERE h.user_id = ?
            AND   d.id = ?
            AND   d.file_exists = 1"""
    try:
        rows = db.execute(query, user_id, deck_id)
        return rows[0] if rows else None
    except Exception as e:
        logger.error(f"get_deck_by_id: a database error occured retrieving deck info for deck_id {deck_id}: {e}")
        return None
