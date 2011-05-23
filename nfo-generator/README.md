How to use
===========

1. Request an API Key from [thetvdb](http://www.thetvdb.com/?tab=apiregister)
2. Put that API key in a tvdb.key file and edit the script so that TVDB_API_FILE points to it
3. Modify ROOT_MEDIA_DIR to the root folder containing all your media files and folders
4. Create a .control.conf file at the root level of every folder containing a tv show (See syntax below)


Syntax of .control.conf file
============================

This file should contain at least one line containing the TVDBID of the show.
For example, for TV Shows "Bones", it would look like this:

    tvdbid: 75682

You can optionaly preset some attributes, that will prevails in all cases:

    tvdbid: 75682
    genre: US TV Show
    title: Bones (US)

Note: This file should be UTF-8 encoded with UNIX lines endings (LF).
