# Kindle2Anki (Web Version)

#### Video Demo: https://youtu.be/HhVS9eMo_2E
#### Description:
This Web Application (currently deployed to https://kindle2anki.lingrify.com) allows Kindle users to create Anki Card Decks for vocabulary they looked up on their Kindle device. Users can select from different online dictionaries for each supported book language (EN, DE, FR, ES, PT) that will be used to look up word definitions, usage examples etc. They can choose from 2 card types (see below). Once a deck is created, downloaded and imported into Anki, users can leverage Anki's rich feature set (in particular spaced repetition) to study the vocabulary they originally looked up on their Kindle device.

##### How to use this Web App
**Kindle2Anki** requires users to register an account, they can then log in with username or email.

To make use of the site users need to upload a copy of their Kindle *vocab.db*, and are subsequently displayed a list of books for which vocabulary had been looked up on *Kindle*, with information on book language, authors, title and number of lookups shown alongside cover images that are pulled from internet resources. 

The customization of card deck creation involves 3 steps:

1. Selection of a **Book**
2. Selection of a  **Online Dictionary** from a set of available dictionaries for the respective book language (i.e. dictionaries for which response parsers have been written by the creator of this app)
3. Select **Card Type** (Do you want looked up word and text passage on the front and the definition and further usage examples on the back, or vice versa)

Upon Deck Creation a download link is displayed.

Also there is a **Deck Creation History** page listing all the decks created by a user with options for download or deletion. 

As user data (though not necessarily sensitive) is uploaded to(vocab.db) or created on (card decks) the server, it is important for users to control which data they leave behind after using the site. As per buttons on the index page a user can always (selectively or summarily) delete their personal data (vocab.db, card decks) from the server or delete their account alltogether. 

Technologies employed:
* mostly Python (This is a Flask App after all)
* a smattering of JavaScript
* HTML + CSS (some vanilla, mostly Bootstrap)
* SQL (using CS50 SQL module)
* some jinja templating

##### Python programs part this utility
* app.py - the main app
* helpers.py - helper functions 
* db_helpers.py - database related helper funtions
* kindle2anki.py - logic around word lookups and card deck creation
* k2a_dictioinaries.py - dictionaries (data structure) of dictioinaries (online language dictionaries)
* k2a_response_parsers - parsers for dictionary responses (much beautiful soup)
* get_bookcover.py - script and functions to fetch book cover images from online resources
