#!/usr/bin/env python
# -*- coding: utf-8 -*-

__author__ = "Mathieu Cadet <mathieu cadet at gmail>"
__version__ = "$Revision: 1.0 $"

# TODO
# - command lines arguments with argparse
# - flexible logging
# - check python version

import os, sys
import re
import codecs
import urllib, urllib2
import xml.etree.ElementTree as ET

TVDB_API_KEY = ""
TVDB_API_FILE = r"/volume1/tools/tvdb.key"
ROOT_MEDIA_DIR = r"/volume1/incoming"
CONTROL_FILE = ".control.conf"
VERBOSE_MODE = False

MEDIA_FILE_EXT = [".avi", ".mkv", ".mov", ".mp4", ".wbem", ".ogm",]
EPISODES_PATTERN = re.compile (r"[sS](?P<season>\d+)[eE](?P<episode>\d+)")
SEASONS_DIR_PATTERN = re.compile (r"[sS][eE][aA][sS][oO][nN]\s+(?P<season>\d+)")
ABSOLUTE_NUMBER_PATTERN = re.compile (r"([\W_]|^)(?P<episode>\d+)[\W_v]")

_content_dirs = []
_nfo_stats = {
    "shows": 0,
    "episodes": 0,
    "covers": 0,
    "thumbs": 0,
}

def load_api_key ():
    global TVDB_API_KEY
    if not TVDB_API_KEY:
        try:
            with codecs.open (TVDB_API_FILE, "r", "utf-8") as key_file:
                TVDB_API_KEY = key_file.readline ().strip ()
        except:
            pass
    if not TVDB_API_KEY:
        print "[E] Unable to load the API KEY at [%s]." % TVDB_API_FILE
        sys.exit (1)
    if VERBOSE_MODE:
        print "[*] Loaded API Key [%s]" % TVDB_API_KEY

def check_service_status ():
    url = "http://www.thetvdb.com/"
    try:
        urllib2.urlopen (url).read ()
        if VERBOSE_MODE:
            print "[*] TVDB.com service is available" 
        return
    except urllib2.HTTPError as herror:
        print "[E] Unable to open %s: %s (HTTP %s)." % (url, herror.msg, herror.code)
    except urllib2.URLError as uerror:
        print "[E] Unable to open %s: %s." % (url, uerror.reason)
    except IOError as ierror:
        print "[E] Unable to write to %s: %s." % (ierror.filename, ierror.strerror)
    print "[E] TVDB.com seems unavailable." 
    print "[E] Goodbye!"
    sys.exit (1)


def on_walkthrough_error (ose_exception):
    print ose_exception

def find_content_dirs ():
    print "[*] Scanning directories looking for [%s] files" % CONTROL_FILE
    # Walk through the folders tree
    for root, dirs, files in os.walk (ROOT_MEDIA_DIR):
        # Look for control files
        if CONTROL_FILE in files:
            _content_dirs.append (root)
            del dirs[:] # prevent from visiting any subdirectories
    print "[*] Found [%i] relevant folders in %s" % (len (_content_dirs), ROOT_MEDIA_DIR)
    for item in _content_dirs:
        print "[+]  ~> %s" % item

def parse_control_file (filepath):
    control_opts = {}
    try:
        with codecs.open (filepath, "r", "utf-8") as control_file:
            for line in control_file:
                key, value = line.split (": ", 1)
                control_opts [key.strip ()] = value.strip ()
    except:
        print "[!] Failed to parse %s" % filepath
    return control_opts
    
def find_media_files (base_dir):
    # find and then identify media files
    # Walk through the folders tree
    media_files = []
    for root, dirs, files in os.walk (base_dir):
        for file in files:
            if os.path.splitext (file)[1].lower () in MEDIA_FILE_EXT:
                season = episode = None

                # Try to find the season first (using the root directory)
                if SEASONS_DIR_PATTERN.search (os.path.basename (root)):
                    season = int (SEASONS_DIR_PATTERN.search (os.path.basename (root)).group ("season"))
                # Try to flag "special" episodes too
                elif re.search ("[sS][pP][eE][cC][iI][aA][lL]", (os.path.basename (root))):
                    season = 0

                # Now try to get the episode number from the filename (using S0XE0X format)
                if EPISODES_PATTERN.search (file):
                    result = EPISODES_PATTERN.search (file)
                    if not season: # Get the season too is it wasn't found before
                        season = int (result.group ("season"))
                    episode = int (result.group ("episode"))

                # Finally try to get the episode number from the filename (using Absolute numbering format)
                if not episode and ABSOLUTE_NUMBER_PATTERN.search (file):
                    episode = int (ABSOLUTE_NUMBER_PATTERN.search (file).group ("episode"))

                if season is None:
                    season = 1
                if episode is None:
                    continue # don't add anything if episode number was not identified correctly

                media_files.append ({"path": os.path.join (root, file),
                                     "season": season,
                                     "episode": episode,})
    return media_files

def fetch_data (control_data, root, files, overwrite=False):
    # Here connect to TVDB and get the information
    # and then call write_metadata for each episode - and the show itself
    # http://thetvdb.com/wiki/index.php?title=Programmers_API
    # 1. http://www.thetvdb.com/api/APIKEY/mirrors.xml.
    # 2. <mirrorpath_zip>/api/<apikey>/series/<seriesid>/all/<language>.zip
    # 3. Process the XML data in <language>.xml and store all <Series> data.
    # 4. Download each series banner in banners.xml and prompt the user to see which they want to keep
    # 5. Use <language>.xml from step 3 to find and store the data associated with your episode.
    # 6. Use <filename> from results in step 5a to download the episode image from <mirrorpath_banners>/banners/<filename>.
    # Update tvshow.nfo only on overwrite mode or if it doesn't exists already
    
    tvshow_details = None
    banners_details = None
    global _nfo_stats
    
    show_details_url = "http://www.thetvdb.com/api/%s/series/%s/all/en.xml" % (TVDB_API_KEY, control_data.get ("tvdbid"))
    show_banners_url_prefix = "http://www.thetvdb.com/banners/"
    
    # Return now if no TVDB ID was found in the control file
    if not control_data.get ("tvdbid"):
        print "[E] No tvdbid was found in [%s]" % root
        return
        
    def indent_xml (elem,  level=0):
        i = "\n" + level * "  "
        if len (elem):
            if not elem.text or not elem.text.strip():
                elem.text = i + "  "
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
            for elem in elem:
                indent_xml (elem, level+1)
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail =  i
    
    def get_xml_content (url):
        try:
            content = ET.ElementTree ()
            if VERBOSE_MODE:
                print "[*] Retrieving %s" % url
            content.parse (urllib2.urlopen (url))
        except urllib2.HTTPError as herror:
            print "[E] Unable to open %s: %s (HTTP %s)." % (url, herror.msg, herror.code)
            content = None
        except urllib2.URLError as uerror:
            print "[E] Unable to open %s: %s." % (url, uerror.reason)
            content = None
        return content
    
    # Fetch TV show information
    if overwrite or not os.path.exists (os.path.join (root, "tvshow.nfo")):
        # fetch data
        tvshow_details = get_xml_content (show_details_url)
        
        if tvshow_details is None:
            return  # don't waste time
        
        show_data = { 
            "id": tvshow_details.findtext ("Series/id"),
            "title": control_data.get ("title", tvshow_details.findtext ("Series/SeriesName")),
            "plot": tvshow_details.findtext ("Series/Overview"),
            "genre": control_data.get ("genre", tvshow_details.findtext ("Series/Genre")),
        }
        print u"[*] Generating [tvshow.nfo] for [%s]" % show_data ["title"]
        # Create xml tree for tvshow.nfo
        xml_tvshow = ET.Element ("tvshow")
        ET.SubElement (xml_tvshow, "title").text = show_data ["title"]
        ET.SubElement (xml_tvshow, "plot").text = show_data ["plot"]
        ET.SubElement (xml_tvshow, "id").text = show_data ["id"]
        ET.SubElement (xml_tvshow, "genre").text = show_data ["genre"]
        indent_xml (xml_tvshow)
        xml_tree = ET.ElementTree (xml_tvshow)
        xml_tree.write (os.path.join (root, "tvshow.nfo"),
                         encoding="utf-8",
                         xml_declaration=True) # This only appeared with py 2.7
        _nfo_stats ["shows"] += 1
            
    # Fetch TV show cover art
    if overwrite or not os.path.exists (os.path.join (root, u"folder.jpg")):
        # fetch and write folder.jpg
        if tvshow_details is None:
            tvshow_details = get_xml_content (show_details_url)
        
        if tvshow_details:
            cover_filename = tvshow_details.findtext ("Series/poster")
            if cover_filename:
                dl_thumb ("%s%s" % (show_banners_url_prefix, cover_filename), os.path.join (root, u"folder.jpg"))
                _nfo_stats ["covers"] += 1

    # Fetch Episode information for each media file
    for file in files:
        episode_details = None
        episode_id = None
        if re.search (r"TVDBID(?P<tvdbid>\d+)", file["path"]):
            episode_id = re.search (r"TVDBID(?P<tvdbid>\d+)", file["path"]).group ("tvdbid")

        if overwrite or not os.path.exists (u"%s.nfo" % os.path.splitext (file["path"])[0]):
            # fetch and write tvshow.nfo
            if tvshow_details is None:
                tvshow_details = get_xml_content (show_details_url)
            
            if tvshow_details:
                for element in tvshow_details.getiterator ("Episode"):
                    if VERBOSE_MODE:
                        print "Target: [S%sE%sID%s], Got: [%s - S%sE%s]" % \
                                    (file ["season"],
                                    file ["episode"],
                                    episode_id,
                                    element.findtext ("EpisodeName"),
                                    element.findtext ("SeasonNumber"),
                                    element.findtext ("EpisodeNumber"))
                    if (int (element.findtext ("SeasonNumber")) == file ["season"] and \
                        int (element.findtext ("EpisodeNumber")) == file ["episode"]) or \
                       (episode_id and element.findtext ("id") == episode_id):
                        episode_details = element
                        break
                
                if episode_details is None:
                    print "[!] No details were found for [%s]" % file ["path"]
                    continue # No details were found, so go to the next file
                    
                episode_data = {
                    "show": tvshow_details.findtext ("Series/SeriesName"),
                    "title": episode_details.findtext ("EpisodeName"),
                    "season": episode_details.findtext ("SeasonNumber"),
                    "episode": episode_details.findtext ("EpisodeNumber"),
                    "rating": episode_details.findtext ("Rating"),
                    "plot": episode_details.findtext ("Overview"),
                    "runtime": tvshow_details.findtext ("Series/Runtime"),
                    "aired": episode_details.findtext ("FirstAired"),
                }
                
                print "[*] Generating NFO file for [%s] - S%sE%s" % (episode_data ["show"], 
                                                                  episode_data ["season"].zfill (2),
                                                                  episode_data ["episode"].zfill(2))
                # Create xml tree for tvshow.nfo
                xml_episode = ET.Element ("episodedetails")
                ET.SubElement (xml_episode, "title").text = episode_data ["title"]
                ET.SubElement (xml_episode, "plot").text = episode_data ["plot"]
                ET.SubElement (xml_episode, "season").text = episode_data ["season"]
                ET.SubElement (xml_episode, "episode").text = episode_data ["episode"]
                ET.SubElement (xml_episode, "rating").text = episode_data ["rating"]
                ET.SubElement (xml_episode, "runtime").text = episode_data ["runtime"]
                ET.SubElement (xml_episode, "aired").text = episode_data ["aired"]
                indent_xml (xml_episode)
                xml_tree = ET.ElementTree (xml_episode)
                xml_tree.write (u"%s.nfo" % os.path.splitext (file["path"])[0],
                                 encoding="utf-8",
                                 xml_declaration=True) # This only appeared with py 2.7
                _nfo_stats ["episodes"] += 1
                
        # Fetch Episode thumbnail
        if overwrite or not os.path.exists (u"%s.tbn" % os.path.splitext (file["path"])[0]):
            # fetch and write tvshow.nfo
            if tvshow_details is None:
                tvshow_details = get_xml_content (show_details_url)
            
            if tvshow_details:
                # try to reuse previous lookup before doing it again
                if episode_details is None:
                    for element in tvshow_details.getiterator ("Episode"):
                        if int (element.findtext ("SeasonNumber")) == file ["season"] and \
                           int (element.findtext ("EpisodeNumber")) == file ["episode"]:
                            episode_details = element
                            break
                
                if episode_details is None: 
                    print "[!] No details were found for [%s]" % file ["path"]
                    continue # No details were found, so go to the next file
                    
                thumb_filename = episode_details.findtext ("filename")
                if thumb_filename:
                    dl_thumb ("%s%s" % (show_banners_url_prefix, thumb_filename),
                                u"%s.tbn" % os.path.splitext (file["path"])[0])
                    _nfo_stats ["thumbs"] += 1

def write_metatada (content, filepath):
    try:
        with codecs.open (filepath, "w", "utf-8") as nfo_file:
            nfo_file.write (content)
    except:
        print "[!] An error occured while writing to %s" % filepath
            
def dl_thumb (url, filepath):
    try:
        if VERBOSE_MODE:
            print "[*] Storing %s" % url
        content = urllib2.urlopen (url)
        with open (filepath, "wb") as img_file:
            img_file.write (content.read ())
    except urllib2.HTTPError as herror:
        print "[E] Unable to open %s: %s (HTTP %s)." % (url, herror.msg, herror.code)
    except urllib2.URLError as uerror:
        print "[E] Unable to open %s: %s." % (url, uerror.reason)
    except IOError as ierror:
        print "[E] Unable to write to %s: %s." % (ierror.filename, ierror.strerror)
        
def show_stats ():
    print "[*] Wrote [%s] tvshow.nfo and [%s] episode .nfo" % (_nfo_stats["shows"], _nfo_stats["episodes"])
    print "[*] Fetched [%s] covers and [%s] episode thumbs" % (_nfo_stats["covers"], _nfo_stats["thumbs"])
                    
def generate_metadata ():
    for item in _content_dirs:
        control = parse_control_file (os.path.join (item, CONTROL_FILE))
        files = find_media_files (item)
        fetch_data (control, item, files, overwrite=False)
    # it may be useful to call os.fsync () at that point
        
def main ():
    print
    load_api_key ()
    check_service_status ()
    find_content_dirs ()
    generate_metadata ()
    show_stats ()
    if sys.platform == "win32":
        os.system ("pause")

if __name__ == "__main__":
    main ()
