What this script does
======================

This script will search for media files corresponding to TV shows for which there
is an entry in [thetvdb.com](http://www.thetvdb.com).

For those who matches, the script will generate:

 * A tvshow.nfo file in the root folder of the show
 * A folder.jpg file in the root folder of the show
 * A .nfo file for each found episode
 * A .tbn file for each found episode

The format used for nfo files is based on the one the [Boxee Box](http://www.boxee.tv) is using.
This script was designed to handle US/UK TV Shows, Japanese Animes and Asian Dramas (JDrama, KDrama & CDrama).

How to use
===========

    usage: nfogen.py [-h] [-o] [-v] [-r ROOT]
                     [-f TVDB_KEY_FILE] [-k TVDB_KEY]

    Generate metadata content (NFOs, TBNs) from media files, to be used by media
    players such as the Boxee Box.

    optional arguments:
      -h, --help            show this help message and exit
      -o, --overwrite
      -v, --verbose
      -r ROOT, --root ROOT
      -f TVDB_KEY_FILE, --tvdb-key-file TVDB_KEY_FILE
      -k TVDB_KEY, --tvdb-key TVDB_KEY


Here is an example showing basic usage:

    ./nfogen.py -k "070010A2303" -r /root/media/folder

This is going to generate metadata for everything located below /root/media/folder
and will use TVDB API key "070010A2303".
You can also put the API Key in a text file and specify that file using the command-line
argument `-f`.

Note:

 * You can request an TVDB API Key from there: [thetvdb.com](http://www.thetvdb.com/?tab=apiregister)
 * Make sure Python 2.7 is installed and run the script
 * You will have to create a .control.conf file at the root level of every folder
   containing a tv show (See syntax below)

Syntax of .control.conf file
============================

This file should contain at least one line containing the TVDB Identifier of the show.
For example, for TV Shows "Bones", it would look like this:

    tvdbid: 75682

You can optionaly preset some attributes, that will prevails in all cases:

    tvdbid: 75682
    genre: US TV Show
    title: Bones (US)

Note: This file should be UTF-8 encoded with UNIX lines endings (LF).
